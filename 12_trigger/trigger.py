# -*- coding: utf-8 -*-
"""trigger.py —— 纯离线软件触发引擎（不接触硬件）。

所有查找均用 numpy 向量化实现；find(data, rate) 返回触发样本索引或 None。
通道编号遵循本机实测映射：CHn -> bitn（0..7）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAX_CHANNEL = 7


def _check_channel(channel: int) -> int:
    """校验通道号，越界抛中文 ValueError。"""
    if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= MAX_CHANNEL:
        raise ValueError(f"通道号必须是 0..{MAX_CHANNEL} 的整数，收到 {channel!r}")
    return channel


def _levels(data: np.ndarray, channel: int) -> np.ndarray:
    """取单通道电平序列（uint8，0/1）。"""
    _check_channel(channel)
    return ((np.asarray(data) >> channel) & 1).astype(np.uint8)


@dataclass
class EdgeTrigger:
    """第 count 个上升沿（rising=True）或下降沿（rising=False）。"""
    channel: int
    rising: bool = True
    count: int = 1

    def __post_init__(self) -> None:
        _check_channel(self.channel)
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count <= 0:
            raise ValueError(f"count 必须是正整数，收到 {self.count!r}")

    def find(self, data: np.ndarray, rate: int) -> int | None:
        b = _levels(data, self.channel)
        if b.size < 2:
            return None
        if self.rising:
            idx = np.flatnonzero((b[1:] == 1) & (b[:-1] == 0)) + 1
        else:
            idx = np.flatnonzero((b[1:] == 0) & (b[:-1] == 1)) + 1
        return int(idx[self.count - 1]) if idx.size >= self.count else None

def _runs(b: np.ndarray, value: int) -> tuple[np.ndarray, np.ndarray]:
    """返回 b 中 value 连续段的 (起点, 终点开区间) 两个下标数组。"""
    m = (b == value).astype(np.int8)
    d = np.diff(np.concatenate((np.zeros(1, np.int8), m, np.zeros(1, np.int8))))
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1)


@dataclass
class LevelTrigger:
    """连续 count 个样本等于 level，返回该连续段的起点。"""
    channel: int
    level: int = 1
    count: int = 1

    def __post_init__(self) -> None:
        _check_channel(self.channel)
        if self.level not in (0, 1):
            raise ValueError(f"level 只能是 0 或 1，收到 {self.level!r}")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count <= 0:
            raise ValueError(f"count 必须是正整数，收到 {self.count!r}")

    def find(self, data: np.ndarray, rate: int) -> int | None:
        b = _levels(data, self.channel)
        if b.size == 0:
            return None
        starts, ends = _runs(b, self.level)
        if starts.size == 0:
            return None
        ok = np.flatnonzero((ends - starts) >= self.count)
        return int(starts[ok[0]]) if ok.size else None

@dataclass
class PulseWidthTrigger:
    """脉宽落在 [min_samples, max_samples] 的脉冲，返回其起点。"""
    channel: int
    min_samples: int | None = None
    max_samples: int | None = None
    polarity: str = 'high'

    def __post_init__(self) -> None:
        _check_channel(self.channel)
        if self.polarity not in ('high', 'low'):
            raise ValueError(f"polarity 只能是 'high' 或 'low'，收到 {self.polarity!r}")
        for name, v in (('min_samples', self.min_samples), ('max_samples', self.max_samples)):
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                raise ValueError(f"{name} 必须是非负整数或 None，收到 {v!r}")
        if (self.min_samples is not None and self.max_samples is not None
                and self.min_samples > self.max_samples):
            raise ValueError('min_samples 不能大于 max_samples')

    def find(self, data: np.ndarray, rate: int) -> int | None:
        b = _levels(data, self.channel)
        if b.size == 0:
            return None
        target = 1 if self.polarity == 'high' else 0
        starts, ends = _runs(b, target)
        if starts.size == 0:
            return None
        lens = ends - starts
        lo = self.min_samples if self.min_samples is not None else 0
        hi = self.max_samples if self.max_samples is not None else b.size
        ok = np.flatnonzero((lens >= lo) & (lens <= hi))
        return int(starts[ok[0]]) if ok.size else None


@dataclass
class PatternTrigger:
    """多通道并行模式匹配，如 '1x0'（x=不关心），返回首个匹配样本。"""
    pattern: str
    channel_map: list[int]

    def __post_init__(self) -> None:
        if not isinstance(self.pattern, str) or not self.pattern:
            raise ValueError('pattern 必须是非空字符串')
        if len(self.pattern) != len(self.channel_map):
            raise ValueError(f"pattern 长度 {len(self.pattern)} 与 channel_map 长度 {len(self.channel_map)} 不一致")
        for c in self.pattern:
            if c not in ('0', '1', 'x'):
                raise ValueError(f"pattern 只能包含 0/1/x，收到非法字符 {c!r}")
        for ch in self.channel_map:
            _check_channel(ch)

    def find(self, data: np.ndarray, rate: int) -> int | None:
        data = np.asarray(data)
        if data.size == 0:
            return None
        mask = np.ones(data.size, dtype=bool)
        for ch, c in zip(self.channel_map, self.pattern):
            if c != 'x':
                mask &= (((data >> ch) & 1) == int(c))
        idx = np.flatnonzero(mask)
        return int(idx[0]) if idx.size else None

@dataclass
class UartStartTrigger:
    """UART 起始位：下降沿且半个 bit 之后仍为低电平。"""
    channel: int
    baud: int
    rate: int

    def __post_init__(self) -> None:
        _check_channel(self.channel)
        if not isinstance(self.baud, int) or self.baud <= 0:
            raise ValueError(f"baud 必须是正整数，收到 {self.baud!r}")
        if not isinstance(self.rate, int) or self.rate <= 0:
            raise ValueError(f"rate 必须是正整数，收到 {self.rate!r}")

    def find(self, data: np.ndarray, rate: int) -> int | None:
        b = _levels(data, self.channel)
        if b.size < 2:
            return None
        falling = np.flatnonzero((b[1:] == 0) & (b[:-1] == 1)) + 1
        if falling.size == 0:
            return None
        half = int(round(self.rate / self.baud / 2))
        probe = falling + half
        valid = probe < b.size
        if not np.any(valid):
            return None
        candidates = falling[valid]
        low_ok = b[probe[valid]] == 0
        ok = np.flatnonzero(low_ok)
        return int(candidates[ok[0]]) if ok.size else None

# --- 触发器定义完毕 ---
