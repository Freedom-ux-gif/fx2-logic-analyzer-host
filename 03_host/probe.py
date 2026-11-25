#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe.py —— Saleae 设备探测与自检（步骤 3）

用法：python -I probe.py
无设备：打印中文提示 + INF 实读 GUID + 设备管理器当前状态，退出码 2。
有设备：打开、查速度、尝试标准 GET_DESCRIPTOR(DEVICE) 控制传输，退出码 0。
无论有无设备，退出码只能是 0 或 2，绝不能是 1（未捕获异常）。
"""
import os
import re
import struct
import sys

# Windows 控制台 GBK 会炸，先重配 UTF-8。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from winusb import (  # noqa: E402
    SaleaeDevice, SaleaeUsbError, enumerate_devices,
    ALL_GUIDS, GUID, INF_PATH, parse_inf_guids,
)


def print_no_device():
    """无设备分支：中文提示 + GUID + 设备管理器状态。"""
    print("未发现已插入的 Saleae 设备，请插入设备后重试。")
    print()
    print("从本机 INF 实读到的设备接口 GUID：")
    for g in (ALL_GUIDS or [GUID]):
        print("  ", g)
    print()
    print("设备管理器里该设备当前状态：")
    # 只读查询 PnP 状态；设备未插入时会留下 Status=Unknown 的幽灵节点。
    # 这里不依赖任何第三方包，直接用 PowerShell（系统自带）查询。
    status_lines = []
    try:
        import subprocess
        ps = (
            "Get-PnpDevice -ErrorAction SilentlyContinue | "
            "Where-Object { $_.InstanceId -like 'USB\\VID_0925*' -or "
            "$_.InstanceId -like 'USB\\VID_21A9*' } | "
            "ForEach-Object { $_.InstanceId + '  Status=' + $_.Status }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15)
        status_lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception as e:  # 查询失败不能变成退出码 1
        status_lines = ["（PnP 状态查询失败：%r）" % (e,)]
    if status_lines:
        for ln in status_lines:
            print("  ", ln)
    else:
        print("   （无匹配节点）")
    print()
    print("提示：Status=Unknown 通常是设备未插入留下的幽灵节点，属正常现象。")


def query_pipe_information(dev):
    """
    查询管道信息。
    WinUsb_QueryPipe 是公开 API，但本库当前未把它列入 winusb.py 的 2.4 必选声明，
    且管道号要等 02_usb 抓包确定；此处如实写未实现，不假装实现。
    """
    print("管道信息：未实现 —— 原因：需要 WinUsb_QueryPipe，且有效 pipeId 依赖")
    print("          02_usb 抓包结果（数据管道端点号尚未确认），避免硬编码错误端点。")


def parse_device_descriptor(blob):
    """解析 18 字节 DEVICE 描述符，返回 (bcdUSB, idVendor, idProduct)。"""
    if len(blob) < 18:
        return None
    # 标准 USB DEVICE 描述符布局（小端）：
    #   bLength(0), bDescriptorType(1), bcdUSB(2:4), ..., idVendor(8:10), idProduct(10:12)
    bcd_usb = struct.unpack_from("<H", blob, 2)[0]
    vid = struct.unpack_from("<H", blob, 8)[0]
    pid = struct.unpack_from("<H", blob, 10)[0]
    return bcd_usb, vid, pid


def main():
    try:
        devs = enumerate_devices()
    except Exception as e:
        # 枚举本身异常也要给中文错误 + 退出码 2，不能是 1。
        print("设备枚举发生异常：%r" % (e,))
        print("从本机 INF 实读到的设备接口 GUID：")
        for g in (ALL_GUIDS or [GUID]):
            print("  ", g)
        return 2

    if not devs:
        print_no_device()
        return 2

    print("发现 %d 个 Saleae 设备：" % len(devs))
    for i, d in enumerate(devs):
        print("  [%d] %s  VID=%04X PID=%04X  路径=%s" %
              (i, d.get("model", "未知"), d.get("vid", 0), d.get("pid", 0), d.get("path", "")))

    dev = SaleaeDevice(devs[0]["path"])
    try:
        dev.open()
        num, name = dev.query_speed()
        print("USB 速度：%d = %s" % (num, name))
        query_pipe_information(dev)
        # 标准 GET_DESCRIPTOR(DEVICE)：bmRequestType=0x80, bRequest=0x06,
        # wValue=0x0100（描述符类型 1=DEVICE，索引 0），读 18 字节。
        try:
            blob = dev.control_transfer(0x80, 0x06, 0x0100, 0x00, b"\x00" * 18)
            parsed = parse_device_descriptor(blob)
            if parsed:
                bcd, vid, pid = parsed
                print("GET_DESCRIPTOR(DEVICE) 返回 %d 字节：" % len(blob))
                print("  bcdUSB=0x%04X  idVendor=0x%04X  idProduct=0x%04X" % (bcd, vid, pid))
            else:
                print("GET_DESCRIPTOR(DEVICE) 返回不足 18 字节（%d 字节），无法解析" % len(blob))
        except SaleaeUsbError as e:
            print("GET_DESCRIPTOR 控制传输失败（不影响脚本退出码）：%s" % (e,))
    except SaleaeUsbError as e:
        print("打开设备失败：%s" % (e,))
        return 2
    except Exception as e:
        print("探测过程中发生未预期异常（转成退出码 2）：%r" % (e,))
        return 2
    finally:
        dev.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
