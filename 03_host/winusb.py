#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
winusb.py —— 纯 ctypes + WinUSB 的 Saleae 底层 USB 库

不依赖 pyusb / libusb / 官方 SDK。只依赖系统自带的 setupapi.dll、
winusb.dll、Kernel32（CreateFileW）。全中文注释。

设计要点：
  * GUID 从本机 Saleae.inf 实读（见 inf_guid.py），不猜、不抄网络。
  * 结构体 cbSize 用 ctypes.sizeof 实测，避免 x86/x64 对齐差异导致的崩溃。
  * 设备未插入时所有枚举函数返回空列表，绝不抛未捕获异常。
  * 同步 I/O（Overlapped 传 None），异步 overlapped 暂未实现。
"""
import ctypes
from ctypes import wintypes
import os
import re
import sys

# Windows 控制台默认 GBK，打印中文说明会炸；统一重配为 UTF-8（大脑实测踩坑）。
if hasattr(sys.stdout, "reconfigure"):
    if sys.stdout is not None:   # PyInstaller --noconsole 下 sys.stdout 为 None
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 让同目录的 inf_guid.py 被 import（python -I 下不自动含脚本目录）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inf_guid import GUID, ALL_GUIDS, INF_PATH, parse_inf_guids  # noqa: E402

# ---------------------------------------------------------------------------
# 1. 设备常量
# ---------------------------------------------------------------------------
# VID/PID 全集：来自本机 Saleae.inf 的 [SaleaeMfg.NTx86/NTamd64] 两节实读。
SALEAE_VID_PIDS = [
    (0x0925, 0x3881),  # Logic（第 16/26 行）
    (0x21A9, 0x1001),  # Logic16（第 17/27 行）
    (0x21A9, 0x1002),  # LogicStart
    (0x21A9, 0x1003),  # Logic4
    (0x21A9, 0x1004),  # Logic8
    (0x21A9, 0x1005),  # LogicPro8
    (0x21A9, 0x1006),  # LogicPro16
]
# PID -> 型号名（与 INF 的 DeviceDesc 字符串一一对应）。
MODEL_NAMES = {
    0x3881: "Logic",
    0x1001: "Logic16",
    0x1002: "LogicStart",
    0x1003: "Logic4",
    0x1004: "Logic8",
    0x1005: "LogicPro8",
    0x1006: "LogicPro16",
}

# ---------------------------------------------------------------------------
# 2. IOCTL 常量（本库不用它们做 I/O，仅为协议对账资料保留）
# ---------------------------------------------------------------------------
# CTL_CODE 公式（来自 Windows DDK devioctl.h）：
#   CTL_CODE(DeviceType, Function, Method, Access) =
#       (DeviceType << 16) | (Access << 14) | (Function << 2) | Method
# 本库固定 DeviceType=FILE_DEVICE_UNKNOWN=0x22，Method=METHOD_BUFFERED=0，
# Access=FILE_ANY_ACCESS=0。于是码值 = 0x220000 | (Function << 2)。
#
# 函数号推导：WinUSB 内部把这一组 IOCTL 按固定顺序排列，从 0 起连续编号：
#   GET_VERSION=0, QUERY_INFORMATION=1, SET_INFORMATION=2,
#   GET_PIPE_POLICY=3, SET_PIPE_POLICY=4, ABORT_PIPE=5, RESET_PIPE=6,
#   FLUSH_PIPE=7。
# 注意：这组 IOCTL 不在公开的 winusb.h/winusbio.h 中（公开头只导出
# WinUsb_* 函数），Logic.exe 的导入表也没有 DeviceIoControl；因此它们不是
# 本库实际通信路径，只作为后续抓包对账的推导值记录。全部走公开的
# WinUsb_* 导出函数，避免依赖内部 IOCTL 的正确性。
def CTL_CODE(device_type, function, method, access):
    """按 DDK 公式合成 IOCTL 控制码。"""
    return ((device_type & 0xFFFF) << 16) | ((access & 0x3) << 14) | \
           ((function & 0xFFF) << 2) | (method & 0x3)


FILE_DEVICE_UNKNOWN = 0x22
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0


def _winusb_ioctl(function):
    """用上面的固定参数算 WinUSB 内部 IOCTL。"""
    return CTL_CODE(FILE_DEVICE_UNKNOWN, function, METHOD_BUFFERED, FILE_ANY_ACCESS)


# 每个常量的推导（function 编号 -> 码值）：
IOCTL_WINUSB_GET_VERSION      = _winusb_ioctl(0)  # fn=0 -> 0x0220000
IOCTL_WINUSB_QUERY_INFORMATION = _winusb_ioctl(1)  # fn=1 -> 0x0220004
IOCTL_WINUSB_SET_INFORMATION   = _winusb_ioctl(2)  # fn=2 -> 0x0220008
IOCTL_WINUSB_GET_PIPE_POLICY   = _winusb_ioctl(3)  # fn=3 -> 0x022000C
IOCTL_WINUSB_SET_PIPE_POLICY   = _winusb_ioctl(4)  # fn=4 -> 0x0220010
IOCTL_WINUSB_ABORT_PIPE        = _winusb_ioctl(5)  # fn=5 -> 0x0220014
IOCTL_WINUSB_RESET_PIPE        = _winusb_ioctl(6)  # fn=6 -> 0x0220018
IOCTL_WINUSB_FLUSH_PIPE        = _winusb_ioctl(7)  # fn=7 -> 0x022001C

# 设备信息类型（公开 winusbio.h 实值）。
DEVICE_SPEED = 0x01
SPEED_NAMES = {0: "未知", 1: "Low", 2: "Full", 3: "High", 4: "Super"}

# 管道策略类型（公开 winusbio.h 实值）。
SHORT_PACKET_TERMINATE = 0x01
AUTO_CLEAR_STALL = 0x02
PIPE_TRANSFER_TIMEOUT = 0x03
IGNORE_SHORT_PACKETS = 0x04
ALLOW_PARTIAL_READS = 0x05
AUTO_FLUSH = 0x06
RAW_IO = 0x07

# CreateFileW 相关常量。
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# SetupAPI 枚举标志。
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10


# ---------------------------------------------------------------------------
# 3. 错误类型
# ---------------------------------------------------------------------------
class SaleaeUsbError(Exception):
    """USB 层的中文可读异常。"""


def _err(code):
    """把 GetLastError 常见码转成中文人话。"""
    return {
        2: "设备不在或被占用（ERROR_FILE_NOT_FOUND）",
        5: "需要 WinUSB 驱动或权限不足（ERROR_ACCESS_DENIED）",
        3: "路径不存在（ERROR_PATH_NOT_FOUND）",
        32: "设备正被另一个进程占用（ERROR_SHARING_VIOLATION）",
        87: "参数错误（ERROR_INVALID_PARAMETER）",
        31: "设备已断开（ERROR_GEN_FAILURE）",
        1167: "设备不存在（ERROR_DEVICE_NOT_CONNECTED）",
    }.get(code, f"Windows 错误码 {code}")


# ---------------------------------------------------------------------------
# 4. Win32 / SetupAPI 结构体与函数声明
# ---------------------------------------------------------------------------
class GUIDStruct(ctypes.Structure):
    """Win32 GUID（= ctypes 的 16 字节数据）。"""
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    """SetupAPI 设备接口数据结构，cbSize 必须是 0x20（32 字节，x86/x64 一致）。"""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUIDStruct),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    """
    设备接口详情头。cbSize 在 64 位必须是 8，32 位才是 6！
    这是最常见的崩溃点：写死 6 在 x64 上会被 SetupAPI 判定缓冲太小而失败。
    这里用 ctypes.sizeof 实测验证：cbSize(4) + wchar 对齐到 8 => 8。
    """
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),  # 尾部柔性数组占位
    ]


class WINUSB_SETUP_PACKET(ctypes.Structure):
    """USB 控制传输 setup 包，必须 8 字节（公开 winusb.h 用 #pragma pack(1)）。"""
    _pack_ = 1
    _fields_ = [
        ("RequestType", ctypes.c_ubyte),
        ("Request", ctypes.c_ubyte),
        ("Value", ctypes.c_ushort),
        ("Index", ctypes.c_ushort),
        ("Length", ctypes.c_ushort),
    ]


# 启动即自检结构体尺寸；不符则直接崩，避免后续出现难以定位的内存破坏。
assert ctypes.sizeof(WINUSB_SETUP_PACKET) == 8, \
    "WINUSB_SETUP_PACKET 必须为 8 字节"
assert ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W) == 8, \
    "x64 下 SP_DEVICE_INTERFACE_DETAIL_DATA_W 的 cbSize 应为 8（32 位为 6）"
assert ctypes.sizeof(SP_DEVICE_INTERFACE_DATA) == 0x20, \
    "SP_DEVICE_INTERFACE_DATA 的 cbSize 必须为 0x20"

# 动态加载系统 DLL（use_last_error=True 才能用 ctypes.get_last_error()）。
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winusb = ctypes.WinDLL("winusb", use_last_error=True)

# --- SetupAPI 声明 ---
setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUIDStruct), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUIDStruct),
    wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

# --- Kernel32 声明 ---
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

# --- WinUSB 声明（全部 restype/argtypes，按公开 winusb.h 填充） ---
_WINUSB_HANDLE = ctypes.c_void_p
winusb.WinUsb_Initialize.restype = wintypes.BOOL
winusb.WinUsb_Initialize.argtypes = [_WINUSB_HANDLE, ctypes.POINTER(_WINUSB_HANDLE)]
winusb.WinUsb_Free.restype = wintypes.BOOL
winusb.WinUsb_Free.argtypes = [_WINUSB_HANDLE]
winusb.WinUsb_QueryDeviceInformation.restype = wintypes.BOOL
winusb.WinUsb_QueryDeviceInformation.argtypes = [
    _WINUSB_HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
winusb.WinUsb_GetPipePolicy.restype = wintypes.BOOL
winusb.WinUsb_GetPipePolicy.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
winusb.WinUsb_SetPipePolicy.restype = wintypes.BOOL
winusb.WinUsb_SetPipePolicy.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
winusb.WinUsb_ControlTransfer.restype = wintypes.BOOL
winusb.WinUsb_ControlTransfer.argtypes = [
    _WINUSB_HANDLE, WINUSB_SETUP_PACKET, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
winusb.WinUsb_ReadPipe.restype = wintypes.BOOL
winusb.WinUsb_ReadPipe.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
winusb.WinUsb_WritePipe.restype = wintypes.BOOL
winusb.WinUsb_WritePipe.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
winusb.WinUsb_AbortPipe.restype = wintypes.BOOL
winusb.WinUsb_AbortPipe.argtypes = [_WINUSB_HANDLE, ctypes.c_ubyte]
winusb.WinUsb_ResetPipe.restype = wintypes.BOOL
winusb.WinUsb_ResetPipe.argtypes = [_WINUSB_HANDLE, ctypes.c_ubyte]
winusb.WinUsb_FlushPipe.restype = wintypes.BOOL
winusb.WinUsb_FlushPipe.argtypes = [_WINUSB_HANDLE, ctypes.c_ubyte]

# 交替设置（Alternate Setting）。Saleae 的 INF 把端点全放在 alt 1 上：
# alt 0 有 0 个端点，alt 1 才有 6 个。WinUsb_Initialize 之后默认停在 alt 0，
# 此时任何 pipe 操作都会返回 ERROR_INVALID_PARAMETER(87)。
# 如果不切到 alt 1，读写和策略设置都会失败。
winusb.WinUsb_SetCurrentAlternateSetting.restype = wintypes.BOOL
winusb.WinUsb_SetCurrentAlternateSetting.argtypes = [_WINUSB_HANDLE, ctypes.c_ubyte]
winusb.WinUsb_GetCurrentAlternateSetting.restype = wintypes.BOOL
winusb.WinUsb_GetCurrentAlternateSetting.argtypes = [
    _WINUSB_HANDLE, ctypes.POINTER(ctypes.c_ubyte)]


class USB_INTERFACE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_ubyte),
        ("bDescriptorType", ctypes.c_ubyte),
        ("bInterfaceNumber", ctypes.c_ubyte),
        ("bAlternateSetting", ctypes.c_ubyte),
        ("bNumEndpoints", ctypes.c_ubyte),
        ("bInterfaceClass", ctypes.c_ubyte),
        ("bInterfaceSubClass", ctypes.c_ubyte),
        ("bInterfaceProtocol", ctypes.c_ubyte),
        ("iInterface", ctypes.c_ubyte),
    ]


winusb.WinUsb_QueryInterfaceSettings.restype = wintypes.BOOL
winusb.WinUsb_QueryInterfaceSettings.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, ctypes.POINTER(USB_INTERFACE_DESCRIPTOR)]


class WINUSB_PIPE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PipeType", wintypes.DWORD),          # 0=Control 1=Iso 2=Bulk 3=Interrupt
        ("PipeId", ctypes.c_ubyte),
        ("MaximumPacketSize", wintypes.USHORT),
        ("Interval", ctypes.c_ubyte),
    ]


winusb.WinUsb_QueryPipe.restype = wintypes.BOOL
winusb.WinUsb_QueryPipe.argtypes = [
    _WINUSB_HANDLE, ctypes.c_ubyte, ctypes.c_ubyte,
    ctypes.POINTER(WINUSB_PIPE_INFORMATION)]

PIPE_TYPE_NAMES = {0: "Control", 1: "Isochronous", 2: "Bulk", 3: "Interrupt"}


def _guid_struct(guid_text):
    """把 '{XXXXXXXX-....}' 字符串转为 GUIDStruct。"""
    g = GUIDStruct()
    hexpart = guid_text.strip("{}").replace("-", "")
    g.Data1 = int(hexpart[0:8], 16)
    g.Data2 = int(hexpart[8:12], 16)
    g.Data3 = int(hexpart[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(hexpart[16 + 2 * i:18 + 2 * i], 16)
    return g


# ---------------------------------------------------------------------------
# 5. 设备枚举
# ---------------------------------------------------------------------------
def enumerate_devices(guids=None):
    """
    枚举当前插入的 Saleae WinUSB 设备。
    返回 [{"path","vid","pid","model"}, ...]；无设备返回 []，不抛异常。
    """
    if guids is None:
        guids = ALL_GUIDS or [GUID]
    results = []
    seen = set()
    for guid_text in guids:
        hdev = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(_guid_struct(guid_text)), None, None,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
        if not hdev or hdev == INVALID_HANDLE_VALUE:
            continue  # 该 GUID 无设备，跳过
        try:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(iface)  # 实测 0x20
            index = 0
            while setupapi.SetupDiEnumDeviceInterfaces(
                    hdev, None, ctypes.byref(_guid_struct(guid_text)),
                    index, ctypes.byref(iface)):
                index += 1
                # 第一次调用只取所需字节数。
                required = wintypes.DWORD(0)
                setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdev, ctypes.byref(iface), None, 0,
                    ctypes.byref(required), None)
                if required.value == 0:
                    continue
                # 分配原始缓冲，头部 cbSize 按 x64=8 / x86=6 实测。
                buf = ctypes.create_string_buffer(required.value)
                detail = ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W)).contents
                detail.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)
                if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                        hdev, ctypes.byref(iface), buf, required.value,
                        ctypes.byref(required), None):
                    continue
                # 从 DevicePath 起始偏移读取路径（偏移由 ctypes 的布局决定=4+padding=8）。
                path_offset = SP_DEVICE_INTERFACE_DETAIL_DATA_W.DevicePath.offset
                path = ctypes.cast(
                    ctypes.addressof(buf) + path_offset, ctypes.c_wchar_p).value
                if not path or path in seen:
                    continue
                seen.add(path)
                m = re.search(r"vid_([0-9a-fA-F]{4})&pid_([0-9a-fA-F]{4})", path)
                vid = int(m.group(1), 16) if m else 0
                pid = int(m.group(2), 16) if m else 0
                results.append({
                    "path": path,
                    "vid": vid,
                    "pid": pid,
                    "model": MODEL_NAMES.get(pid, "未知型号"),
                    "guid": guid_text,
                })
                iface = SP_DEVICE_INTERFACE_DATA()
                iface.cbSize = ctypes.sizeof(iface)
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return results


# ---------------------------------------------------------------------------
# 6. SaleaeDevice：打开 / 控制传输 / 管道读写
# ---------------------------------------------------------------------------
class SaleaeDevice:
    """一个已打开的 Saleae USB 设备（同步 I/O）。"""

    def __init__(self, path):
        self.path = path
        self.handle = None      # CreateFileW 返回的句柄
        self.usb_handle = None  # WinUsb_Initialize 返回的接口句柄
        self.speed = 0

    def open(self):
        """CreateFileW + WinUsb_Initialize，并查询 USB 速度。"""
        self.handle = kernel32.CreateFileW(
            self.path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            None)
        if not self.handle or self.handle == INVALID_HANDLE_VALUE:
            code = ctypes.get_last_error()
            raise SaleaeUsbError(f"打开设备失败：{_err(code)}；路径={self.path}")
        uh = _WINUSB_HANDLE()
        if not winusb.WinUsb_Initialize(ctypes.c_void_p(self.handle), ctypes.byref(uh)):
            code = ctypes.get_last_error()
            kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None
            raise SaleaeUsbError(f"WinUsb_Initialize 失败：{_err(code)}")
        self.usb_handle = ctypes.c_void_p(uh.value)
        # Saleae 把端点都放在 alternate setting 1 上（alt 0 端点数为 0）。
        # 不切过去的话，所有 pipe 操作都会 ERROR_INVALID_PARAMETER。
        self.alt_setting = 0
        self._select_endpoint_alt_setting()
        # 查速度：DEVICE_SPEED(0x01)，返回 1 字节。
        speed = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(8)
        length = wintypes.DWORD(8)
        if winusb.WinUsb_QueryDeviceInformation(
                self.usb_handle, DEVICE_SPEED, ctypes.byref(length), buf):
            self.speed = buf.raw[0]
        return self

    def _select_endpoint_alt_setting(self):
        """找到带端点的 alternate setting 并切过去。

        Saleae 的接口描述符里 alt 0 是 0 个端点，alt 1 才有端点（6 个）。
        WinUsb_Initialize 默认停在该接口的 alt 0，因此必须显式切换。
        """
        desc = USB_INTERFACE_DESCRIPTOR()
        if not winusb.WinUsb_QueryInterfaceSettings(self.usb_handle, 0, ctypes.byref(desc)):
            return False, 0
        if desc.bNumEndpoints > 0:
            self.alt_setting = desc.bAlternateSetting
            return True, desc.bNumEndpoints
        # alt 0 没有端点：逐个试 alt setting，找第一个有端点的。
        for alt in range(1, 8):
            if not winusb.WinUsb_QueryInterfaceSettings(self.usb_handle, alt,
                                                        ctypes.byref(desc)):
                break
            if desc.bNumEndpoints > 0:
                if winusb.WinUsb_SetCurrentAlternateSetting(self.usb_handle, alt):
                    self.alt_setting = alt
                    return True, desc.bNumEndpoints
                break
        return False, 0

    def list_pipes(self):
        """枚举当前接口下的所有管道，返回 [(pipe_id, 类型名, 最大包长, interval)]。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        desc = USB_INTERFACE_DESCRIPTOR()
        if not winusb.WinUsb_QueryInterfaceSettings(
                self.usb_handle, self.alt_setting, ctypes.byref(desc)):
            raise SaleaeUsbError(f"查询接口设置失败：{_err(ctypes.get_last_error())}")
        out = []
        for idx in range(desc.bNumEndpoints):
            pi = WINUSB_PIPE_INFORMATION()
            if winusb.WinUsb_QueryPipe(self.usb_handle, self.alt_setting, idx,
                                       ctypes.byref(pi)):
                out.append((pi.PipeId, PIPE_TYPE_NAMES.get(pi.PipeType, "?"),
                            pi.MaximumPacketSize, pi.Interval))
        return out

    def query_speed(self):
        """返回 (数字速度, 人话名称)。"""
        return self.speed, SPEED_NAMES.get(self.speed, f"未知({self.speed})")

    def control_transfer(self, request_type, request, value, index, data=b""):
        """USB 控制传输；data 是 host->device 的输出数据；返回收到的 bytes。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        pkt = WINUSB_SETUP_PACKET()
        pkt.RequestType = request_type & 0xFF
        pkt.Request = request & 0xFF
        pkt.Value = value & 0xFFFF
        pkt.Index = index & 0xFFFF
        pkt.Length = len(data) & 0xFFFF
        in_buf = ctypes.create_string_buffer(data) if data else None
        out_buf = ctypes.create_string_buffer(max(len(data), 1))
        transferred = wintypes.DWORD(0)
        ok = winusb.WinUsb_ControlTransfer(
            self.usb_handle, pkt, in_buf if in_buf else out_buf,
            len(data), ctypes.byref(transferred), None)  # overlapped=None 同步
        if not ok:
            raise SaleaeUsbError(
                f"控制传输失败：{_err(ctypes.get_last_error())}")
        return out_buf.raw[:transferred.value]

    def read_pipe(self, pipe_id, length, timeout_ms=1000):
        """从管道读 length 字节；先设置管道超时，再同步读。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        self.set_pipe_policy(pipe_id, PIPE_TRANSFER_TIMEOUT, timeout_ms)
        buf = ctypes.create_string_buffer(length)
        transferred = wintypes.DWORD(0)
        ok = winusb.WinUsb_ReadPipe(
            self.usb_handle, pipe_id & 0xFF, buf, length,
            ctypes.byref(transferred), None)
        if not ok:
            raise SaleaeUsbError(f"读管道 0x{pipe_id:02X} 失败：{_err(ctypes.get_last_error())}")
        return buf.raw[:transferred.value]

    def write_pipe(self, pipe_id, data, timeout_ms=1000):
        """向管道写数据；返回实际写入字节数。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        self.set_pipe_policy(pipe_id, PIPE_TRANSFER_TIMEOUT, timeout_ms)
        buf = ctypes.create_string_buffer(data)
        transferred = wintypes.DWORD(0)
        ok = winusb.WinUsb_WritePipe(
            self.usb_handle, pipe_id & 0xFF, buf, len(data),
            ctypes.byref(transferred), None)
        if not ok:
            raise SaleaeUsbError(f"写管道 0x{pipe_id:02X} 失败：{_err(ctypes.get_last_error())}")
        return transferred.value

    def set_pipe_policy(self, pipe_id, policy_type, value):
        """设置管道策略；value 为 4 字节整数或 bytes。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        if isinstance(value, int):
            val = ctypes.c_uint32(value)
            ptr, size = ctypes.byref(val), 4
        else:
            val = ctypes.create_string_buffer(value)
            ptr, size = val, len(value)
        if not winusb.WinUsb_SetPipePolicy(
                self.usb_handle, pipe_id & 0xFF, policy_type, size, ptr):
            raise SaleaeUsbError(f"设置管道策略失败：{_err(ctypes.get_last_error())}")

    def get_pipe_policy(self, pipe_id, policy_type, size=4):
        """读取管道策略，返回原始 bytes。"""
        if self.usb_handle is None:
            raise SaleaeUsbError("设备未 open()")
        buf = ctypes.create_string_buffer(size)
        length = wintypes.DWORD(size)
        if not winusb.WinUsb_GetPipePolicy(
                self.usb_handle, pipe_id & 0xFF, policy_type,
                ctypes.byref(length), buf):
            raise SaleaeUsbError(f"读取管道策略失败：{_err(ctypes.get_last_error())}")
        return buf.raw[:length.value]

    def abort_pipe(self, pipe_id):
        if not winusb.WinUsb_AbortPipe(self.usb_handle, pipe_id & 0xFF):
            raise SaleaeUsbError(f"中止管道失败：{_err(ctypes.get_last_error())}")

    def reset_pipe(self, pipe_id):
        if not winusb.WinUsb_ResetPipe(self.usb_handle, pipe_id & 0xFF):
            raise SaleaeUsbError(f"复位管道失败：{_err(ctypes.get_last_error())}")

    def flush_pipe(self, pipe_id):
        if not winusb.WinUsb_FlushPipe(self.usb_handle, pipe_id & 0xFF):
            raise SaleaeUsbError(f"冲洗管道失败：{_err(ctypes.get_last_error())}")

    def close(self):
        """释放 WinUSB 接口句柄与文件句柄，可重复调用。"""
        if self.usb_handle is not None:
            winusb.WinUsb_Free(self.usb_handle)
            self.usb_handle = None
        if self.handle is not None:
            kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ---------------------------------------------------------------------------
# 7. 自检入口
# ---------------------------------------------------------------------------
def main():
    devs = enumerate_devices()
    if devs:
        print("发现 %d 个 Saleae 设备：" % len(devs))
        for d in devs:
            print("  ", d)
    else:
        print("枚举结果：[] —— 未发现设备，请插入（或设备被占用/驱动未装）")
    print("INF 实读 GUID（D:\\Program Files\\Saleae Inc\\Drivers\\Saleae.inf）：")
    for g in (ALL_GUIDS or [GUID]):
        print("  ", g)
    print("WINUSB_SETUP_PACKET sizeof =", ctypes.sizeof(WINUSB_SETUP_PACKET))
    print("SP_DEVICE_INTERFACE_DETAIL_DATA_W sizeof =",
          ctypes.sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
    return 0 if devs else 2  # 无设备返回 2，与 probe.py 一致；这里只做自检不强制。


if __name__ == "__main__":
    sys.exit(main())
