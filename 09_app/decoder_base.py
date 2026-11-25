# -*- coding: utf-8 -*-
"""decoder_base.py —— 纯 Python 数字协议解码器的公共基础设施。

本模块提供三样东西：
    1. SampleStream：把 Saleae 逻辑分析仪采集到的原始字节流包装成可查询的采样流；
    2. DecodeEvent：解码产生的一个事件（起始位、字节、地址、应答等）；
    3. Decoder：所有具体协议解码器的抽象基类。

数据格式说明（2026-11-25 真机实测修正）：
    每字节 8 个通道，1 字节 = 8 个通道在同一采样时刻的电平。

    ★ 通道位序（本机克隆板实测）：CH0 -> bit0（LSB），CH7 -> bit7（MSB）
      即 CHn 的电平为 (val >> n) & 1，自然映射。

    这条与 sigrok 文档描述的「Probe 1 在 MSB、Probe 8 在 LSB」相反，
    实测依据：示波器 8kHz 方波接在板子标号 CH0 上，采到的数据只有
    bit0 在 254(0b11111110) / 255(0b11111111) 之间变化，其余 7 位恒为 1
    （未接通道内部上拉为高）。见 08_fx2/capture_verified.py 的实测输出。

    通道编号因此采用 0..7（与板子丝印一致）。为兼容旧代码，
    ch=8 会被当作 bit7 处理（8-8=0 -> 位移 7）——不推荐，优先用 0..7。
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# 强制标准输出使用 UTF-8，避免中文注释/事件内容在 Windows 控制台乱码。
if sys.stdout is not None:   # PyInstaller --noconsole 下 sys.stdout 为 None
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class SampleStream:
    """原始采样字节流的只读包装。

    Attributes:
        raw: 原始字节流（bytes）。
        rate: 采样率（Hz）。
        n_samples: 采样点数，等于 len(raw)。
        duration_s: 整段采集的时长（秒）。
    """

    def __init__(self, data: bytes, sample_rate: int) -> None:
        if sample_rate <= 0:
            raise ValueError(f'采样率必须为正整数，收到 {sample_rate}')
        self.raw: bytes = bytes(data)          # 固定为不可变 bytes，防止外部改动
        self.rate: int = int(sample_rate)
        self.n_samples: int = len(self.raw)

    @property
    def duration_s(self) -> float:
        """整段流的时长（秒）。"""
        return self.n_samples / self.rate

    def channel_bits(self, ch: int) -> np.ndarray:
        """返回某通道的电平序列，形状为 (n_samples,) 的 uint8 数组（取值 0/1）。

        通道编号 0..7，直接对应 bit 位置：CH0 -> bit0 ... CH7 -> bit7。
        这是本机克隆板的实测映射（见模块文档）。

        兼容说明：允许传 8，按 bit7 处理（等价于 CH7），仅为不破坏旧调用。
        新代码请统一用 0..7。
        """
        if not isinstance(ch, int) or isinstance(ch, bool) or not (0 <= ch <= 8):
            raise ValueError(f'通道号必须是 0..7 的整数（允许 8 兼容旧代码），收到 {ch!r}')
        bit = 7 if ch == 8 else ch
        if self.n_samples == 0:
            return np.zeros(0, dtype=np.uint8)
        vals = np.frombuffer(self.raw, dtype=np.uint8)   # 向量化：一次拿到全部采样字节
        return ((vals >> bit) & 1).astype(np.uint8)

    def sample_to_time(self, n: int) -> float:
        """采样序号 -> 秒。"""
        return n / self.rate

    def time_to_sample(self, t: float) -> int:
        """秒 -> 最近的采样序号（四舍五入）。"""
        return int(round(t * self.rate))


@dataclass
class DecodeEvent:
    """一次解码事件。

    start_sample / end_sample 为事件覆盖的采样区间（左闭右开意义上的边界）。
    kind 为事件类型，例如 'start'/'bit'/'byte'/'ack'/'frame'。
    data 为协议相关的附加字段字典。
    """

    start_sample: int
    end_sample: int
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def start_time(self, rate: int) -> float:
        """事件起始时刻（秒）。"""
        return self.start_sample / rate

    def end_time(self, rate: int) -> float:
        """事件结束时刻（秒）。"""
        return self.end_sample / rate

    def __repr__(self) -> str:
        """人类可读的一行摘要。"""
        return (f'DecodeEvent(kind={self.kind!r}, '
                f'samples=[{self.start_sample},{self.end_sample}), '
                f'data={self.data!r})')


class Decoder(ABC):
    """所有协议解码器的抽象基类。"""

    name: str = 'base'

    def __init__(self, stream: SampleStream, **opts: Any) -> None:
        self.stream = stream
        self.opts = opts

    @abstractmethod
    def decode(self) -> list[DecodeEvent]:
        """执行解码，返回事件列表。子类必须实现。"""
        raise NotImplementedError

    def summary(self, events: list[DecodeEvent]) -> str:
        """默认实现：统计各类事件数量，返回一行中文摘要。"""
        counts: dict[str, int] = {}
        for ev in events:
            counts[ev.kind] = counts.get(ev.kind, 0) + 1
        if not counts:
            return f'{self.name}: 0 个事件'
        parts = [f'{k}={v}' for k, v in sorted(counts.items())]
        return f'{self.name}: {len(events)} 个事件（' + ', '.join(parts) + '）'
