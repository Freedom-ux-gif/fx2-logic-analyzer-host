# -*- coding: utf-8 -*-
"""triggered_capture.py —— 带预触发的软件触发采集器。

底层只包装 08_fx2/capture_verified.py（只读复用，不修改）：
一次性采满内存 -> 离线找触发 -> 裁剪出触发前后的数据。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

# 便携化：底层模块位于同级 08_fx2 目录，按相对路径加入搜索路径（不写死本机绝对路径）。
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '08_fx2'))

import capture_verified as cv


@dataclass
class TriggerResult:
    """一次触发采集的结果。所有字段均为可序列化基础类型。"""
    data: np.ndarray
    trigger_index: int | None
    trigger_offset: int | None
    pre_samples: int
    post_samples: int
    rate_hz: int
    found: bool
    message: str = field(default='')

    def __len__(self) -> int:
        return len(self.data)

class TriggeredCapture:
    """采一段 -> 离线找触发 -> 裁出触发前 pre_trigger_ratio 比例的数据。"""

    def __init__(self, device, rate_hz: int, trigger, pre_trigger_ratio: float = 0.2):
        if rate_hz not in cv.BY_HZ:
            raise ValueError(f"不支持的采样率 {rate_hz} Hz，可选：{sorted(cv.BY_HZ)}")
        if not 0.0 <= pre_trigger_ratio < 1.0:
            raise ValueError(f"pre_trigger_ratio 必须在 [0,1) 内，收到 {pre_trigger_ratio!r}")
        self.device = device
        self.rate_hz = rate_hz
        self.delay = cv.BY_HZ[rate_hz][0]
        self.trigger = trigger
        self.pre_trigger_ratio = float(pre_trigger_ratio)

    def run(self, total_seconds: float, max_wait_seconds: float | None = None) -> TriggerResult:
        """采集并查找触发。max_wait_seconds 不限时则只采一段。"""
        own_device = self.device is None
        dev = cv.open_dev() if own_device else self.device
        if dev is None:
            return TriggerResult(np.array([], dtype=np.uint8), None, None, 0, 0,
                                 self.rate_hz, False, '未能打开设备')
        start_wait = time.monotonic()
        last = None
        try:
            while True:
                blob, _ = cv.capture_timed(dev, self.delay, total_seconds, n_readers=3)
                raw = np.frombuffer(blob, dtype=np.uint8).copy()
                last = raw
                n = len(raw)
                # 开头是启动瞬态/残留数据，不参与触发判断；触发点必在预触发余量之后。
                pre = int(n * self.pre_trigger_ratio)
                idx = None if n == 0 else self.trigger.find(raw[pre:], self.rate_hz)
                if idx is not None:
                    idx += pre
                    # 裁剪：触发前占 ratio，触发后用尽剩余样本。
                    post = n - idx
                    length = min(n, int(post / (1.0 - self.pre_trigger_ratio)))
                    pre_n = length - post
                    first = max(0, idx - pre_n)
                    cut = raw[first:first + length]
                    return TriggerResult(cut, idx, idx - first, pre_n, post,
                                         self.rate_hz, True, '已找到触发条件')
                if max_wait_seconds is None or time.monotonic() - start_wait >= max_wait_seconds:
                    break
            return TriggerResult(last, None, None, 0, len(last), self.rate_hz, False,
                                 '未找到触发条件，返回完整采集')
        finally:
            if own_device:
                try:
                    dev.close()
                except Exception:
                    pass

