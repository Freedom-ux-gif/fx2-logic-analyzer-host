"""逻辑分析仪采集核心库（稳定、可复用、可打包）。

封装 08_fx2/capture_verified.py 的实测成果，提供：
  * LogicDevice   —— 设备管理、并发保护、原始数据落盘
  * CaptureResult —— 采集结果与统计

本文件只读复用后端，不修改 08_fx2 / 03_host 中任何代码。
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

# python -I 不会把脚本目录加入 sys.path，这里显式补齐三处路径。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
# PyInstaller onefile 下数据文件解包到 _MEIPASS，需要显式加入搜索路径。
_MEIPASS = getattr(sys, "_MEIPASS", None) or os.environ.get("_MEIPASS2")
for _base in (_ROOT, _HERE, _MEIPASS):
    if not _base:
        continue
    for _p in (os.path.join(_base, "08_fx2"), os.path.join(_base, "03_host")):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)

_backend = None

# 设备只允许一个进程/句柄独占打开，所以所有 LogicDevice 实例共享同一底层句柄，
# 用引用计数决定何时真正关闭。采集互斥锁也必须是模块级的（跨实例生效）。
_shared_dev = None
_shared_lock = threading.Lock()
_refcount = 0
_capture_lock = threading.Lock()


class _DummyStream:
    """--noconsole 打包时 sys.stdout 为 None，提供一个安全的替身。"""

    def reconfigure(self, *args, **kwargs):
        pass

    def write(self, text):
        return len(text)

    def flush(self):
        pass


def backend():
    """延迟加载后端，保证 GUI 在设备不在或后端缺失时也能启动。"""
    global _backend
    if _backend is None:
        if sys.stdout is None:
            sys.stdout = _DummyStream()
        if sys.stderr is None:
            sys.stderr = _DummyStream()
        # 冻结环境下 PyInstaller 对 ctypes 做了裁剪，winusb.py 里的
        # `from ctypes import wintypes` 会失败。先注册标准库 wintypes 再导入。
        if "ctypes.wintypes" not in sys.modules:
            import importlib
            importlib.import_module("ctypes.wintypes")
        import capture_verified
        import winusb
        _backend = (capture_verified, winusb)
    return _backend


class LogicError(RuntimeError):
    """面向用户的中文错误。"""


def find_device():
    """返回第一个 VID 0925 / PID 3881 设备的信息字典，没有则返回 None。"""
    _, usb = backend()
    for d in usb.enumerate_devices():
        if d.get("vid") == 0x0925 and d.get("pid") == 0x3881:
            return d
    return None


def _pretty_name(name: str) -> str:
    """把 '4MHz' 规范成 '4 MHz'，'500kHz' 规范成 '500 kHz'。"""
    for unit in ("MHz", "kHz"):
        if name.endswith(unit):
            return name[:-len(unit)] + " " + unit
    return name


@dataclass
class CaptureResult:
    """一次采集的结果与统计。channel() 返回 0/1 的 numpy 数组。"""

    data: bytes
    rate_hz: int
    elapsed: float
    n_samples: int
    raw_path: str = ""

    def actual_rate(self) -> float:
        """实际采样率（样本/秒）。"""
        return self.n_samples / self.elapsed if self.elapsed > 0 else 0.0

    def achievement(self) -> float:
        """达成率 = 实际采样率 / 标称采样率，用于提示是否丢数据。"""
        return self.actual_rate() / self.rate_hz if self.rate_hz else 0.0

    def channel(self, ch: int) -> np.ndarray:
        """取 0..7 号通道（CH0 对应 bit0）的 0/1 位流。"""
        if not isinstance(ch, int) or not 0 <= ch <= 7:
            raise LogicError("通道号必须是 0 到 7 的整数")
        bits = np.frombuffer(self.data, dtype=np.uint8)
        return (bits >> ch) & 1

    def summary(self) -> str:
        """中文一句话摘要。"""
        cap, _ = backend()
        name = next((n for hz, _, n in cap.RATES if hz == self.rate_hz),
                    f"{self.rate_hz} Hz")
        return (f"采用 {_pretty_name(name)} 采 {self.elapsed:.2f} 秒，"
                f"共 {self.n_samples:,} 样本，达成率 {self.achievement() * 100:.1f}%")


class LogicDevice:
    """一台逻辑分析仪。支持 with 语法；close() 可安全重复调用。"""

    def __init__(self, auto_open: bool = False):
        self._cap_lock = _capture_lock   # 跨实例共享：同一时刻只允许一次采集
        self._owns = False
        if auto_open:
            self.open()

    def open(self):
        """打开设备；设备不在或忙时抛出中文异常。"""
        global _shared_dev, _refcount
        with _shared_lock:
            if self._owns:
                return self
            if _shared_dev is None:
                cap, usb = backend()
                try:
                    devs = usb.enumerate_devices()
                except Exception as exc:
                    raise LogicError(f"枚举设备失败：{exc}") from exc
                if not any(d.get("vid") == 0x0925 and d.get("pid") == 0x3881
                           for d in devs):
                    raise LogicError("未找到逻辑分析仪（VID 0925 PID 3881），请检查 USB 连接")
                try:
                    _shared_dev = cap.open_dev()
                except Exception as exc:
                    raise LogicError(f"设备忙或掉线，打开失败：{exc}") from exc
                if _shared_dev is None:
                    raise LogicError("设备忙或掉线，打开失败：设备未响应")
            _refcount += 1
            self._owns = True
        return self

    def close(self):
        """关闭设备，可安全重复调用；会等待正在进行的采集结束。"""
        global _shared_dev, _refcount
        with _capture_lock:
            with _shared_lock:
                if not self._owns:
                    return
                self._owns = False
                _refcount -= 1
                if _refcount <= 0 and _shared_dev is not None:
                    try:
                        _shared_dev.close()
                    except Exception:
                        pass
                    _shared_dev = None
                    _refcount = 0

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def is_ready(self) -> tuple[bool, str]:
        """返回 (是否可用, 中文原因)；同时检查设备与端点 0x82。"""
        if find_device() is None:
            return False, "未检测到设备（VID 0925 PID 3881），请检查 USB 连接"
        try:
            eps = self.endpoints()
        except LogicError as exc:
            return False, str(exc)
        if 0x82 not in eps:
            return False, ("未检测到数据端点 0x82，请先启动一次 Logic.exe，"
                           "识别到设备后关闭，然后重试")
        return True, "设备就绪：VID 0925 PID 3881 在线，端点 0x82 可用"

    def endpoints(self) -> list[int]:
        """返回当前端点号列表，必要时自动打开设备。"""
        global _shared_dev
        self.open()
        try:
            return [int(p) for p, _, _, _ in _shared_dev.list_pipes()]
        except Exception as exc:
            raise LogicError(f"读取端点失败，设备可能掉线：{exc}") from exc

    def rates(self) -> list[dict]:
        """返回全部可选采样率。"""
        cap, _ = backend()
        return [{"hz": hz, "delay": delay, "name": _pretty_name(name)}
                for hz, delay, name in cap.RATES]

    def capture(self, rate_hz: int, seconds: float, n_readers: int = 3) -> CaptureResult:
        """采集数据；并发调用会立即抛中文异常。原始数据同时写入临时目录。"""
        cap, _ = backend()
        match = next((d for hz, d, _ in cap.RATES if hz == rate_hz), None)
        if match is None:
            raise LogicError(f"不支持的采样率 {rate_hz} Hz，请用 rates() 查看可选值")
        if not self._cap_lock.acquire(blocking=False):
            raise LogicError("上一次采集尚未结束")
        try:
            self.open()
            try:
                blob, _measured = cap.capture_timed(_shared_dev, match, seconds,
                                                    n_readers=n_readers)
            except Exception as exc:
                raise LogicError(f"采集失败，设备忙或掉线：{exc}") from exc
            # 后端停止读线程前会多流一小段 FIFO 尾数；裁到用户请求的时长，
            # 保证样本数与 seconds 对应。达成率用“实际样本 / 标称时长”计算，
            # 大于 1 说明设备满速，低于 1 说明丢数据。
            limit = int(rate_hz * seconds)
            data = blob[:limit] if 0 < limit < len(blob) else blob
            elapsed = float(seconds)
            stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1000000:06d}"
            path = os.path.join(tempfile.gettempdir(), f"logic_capture_{stamp}.bin")
            with open(path, "wb") as fh:
                fh.write(data)
            return CaptureResult(data=data, rate_hz=rate_hz, elapsed=elapsed,
                                 n_samples=len(data), raw_path=path)
        finally:
            self._cap_lock.release()
