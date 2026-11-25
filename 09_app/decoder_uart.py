# -*- coding: utf-8 -*-
"""decoder_uart.py —— 纯 Python 的 UART（异步串口）解码器。

UART 帧结构（空闲为高电平时）：
    空闲(1) -> 起始位(0) -> D0(LSB) ... D7 -> [校验位] -> 停止位(1) -> 空闲

关键约定（来自契约，必须严格遵守）：
    - 空闲电平 idle_high=True 时为 1；起始位是从 1 到 0 的跳变。
    - samples_per_bit = rate / baud（允许非整数）。
    - 起始位中点验证：跳变后 spb/2 个样本处必须仍为 0，否则视为噪声丢弃。
    - 第 k 个数据位（k=0 是 LSB）的采样点 = 跳变位置 + spb*(1.5 + k)。
    - 校验位 even/odd；停止位必须为 idle 电平。
    - 采样点越过流末尾时安全退出，不抛异常。
边沿检测使用 numpy 向量化完成，逐帧处理只遍历边沿而非逐样本。
"""

from __future__ import annotations

import numpy as np

from decoder_base import DecodeEvent, SampleStream, Decoder


class UartDecoder(Decoder):
    """UART 解码器。"""

    name = 'uart'

    def __init__(
        self,
        stream: SampleStream,
        channel: int = 0,
        baud: int = 115200,
        idle_high: bool = True,
        data_bits: int = 8,
        parity: str = 'none',
        stop_bits: int = 1,
        **opts: object,
    ) -> None:
        super().__init__(stream, **opts)
        if not (0 <= channel <= 8):
            raise ValueError(f'channel 必须是 0..7（允许 8 兼容），收到 {channel}')
        if baud <= 0:
            raise ValueError(f'baud 必须为正，收到 {baud}')
        if parity not in ('none', 'even', 'odd'):
            raise ValueError(f'parity 必须是 none/even/odd，收到 {parity!r}')
        if not (1 <= data_bits <= 8):
            raise ValueError(f'data_bits 必须是 1..8，收到 {data_bits}')
        if stop_bits < 1:
            raise ValueError(f'stop_bits 至少为 1，收到 {stop_bits}')
        self.channel = channel
        self.baud = baud
        self.idle_high = idle_high
        self.data_bits = data_bits
        self.parity = parity
        self.stop_bits = stop_bits
        self.spb = stream.rate / baud          # 每位对应的样本数（浮点，保留精度）
        self.idle = 1 if idle_high else 0      # 空闲电平
        self.mark = 0 if idle_high else 1      # 起始位电平（idle 的反面）

    def _sample_at(self, start_edge: int, k: float) -> int:
        """计算某一位的采样样本下标。k=1.5 是起始位中点，k=2.5 是 D0 中点……"""
        return int(round(start_edge + self.spb * k))

    def decode(self) -> list[DecodeEvent]:
        """向量化找起始位跳变，再逐帧解码，返回事件列表。"""
        n = self.stream.n_samples
        events: list[DecodeEvent] = []
        if n < 2:
            return events
        bits: np.ndarray = self.stream.channel_bits(self.channel)

        # 向量化边沿检测：找出所有从 idle 到 mark 的跳变位置（mark 跳变的下标）。
        idle_arr = bits[:-1] == self.idle
        mark_arr = bits[1:] == self.mark
        falling = np.flatnonzero(idle_arr & mark_arr) + 1   # 跳变后第一个 mark 样本的下标

        cursor = 0                     # 已处理到的样本位置，防止把数据位的下降沿误判为起始位
        for edge in falling:
            edge = int(edge)
            if edge < cursor:
                continue
            # 起始位中点验证：确认仍为 mark 电平，否则当噪声丢弃。
            mid = self._sample_at(edge, 0.5)
            if mid >= n or int(bits[mid]) != self.mark:
                cursor = edge + 1
                continue

            # 起始位事件覆盖起始位区间。
            start_end = min(n, self._sample_at(edge, 1.0))
            events.append(DecodeEvent(edge, start_end, 'start',
                                      {'channel': self.channel, 'baud': self.baud}))

            # 逐位采样（LSB first）。第 k 位采样点下标记为 k_index = 1.5 + k。
            value = 0
            for k in range(self.data_bits):
                idx = self._sample_at(edge, 1.5 + k)
                if idx >= n:                       # 采样点越界：安全结束整帧
                    return events
                bit = int(bits[idx])
                value |= bit << k                  # LSB 先到，放到第 k 位

            # 校验位：统计数据中 1 的个数。
            ones = bin(value).count('1')
            parity_idx = self._sample_at(edge, 1.5 + self.data_bits)
            if self.parity != 'none':
                if parity_idx >= n:
                    return events
                rx_parity = int(bits[parity_idx])
                expected = (ones % 2) if self.parity == 'even' else ((ones + 1) % 2)
                if rx_parity != expected:
                    events.append(DecodeEvent(parity_idx, parity_idx + 1, 'parity_error',
                                              {'expected': expected, 'actual': rx_parity,
                                               'value': value}))

            # 停止位验证：必须在 idle 电平。可用 stop_bits 个停止位逐一检查。
            framing_bad = False
            stop_first = self._sample_at(
                edge, 1.5 + self.data_bits + (1 if self.parity != 'none' else 0))
            for s in range(self.stop_bits):
                idx = self._sample_at(
                    edge,
                    1.5 + self.data_bits + (1 if self.parity != 'none' else 0) + s)
                if idx >= n:
                    return events
                if int(bits[idx]) != self.idle:
                    framing_bad = True
            parity_n = 1 if self.parity != 'none' else 0
            byte_span_end = min(n, self._sample_at(
                edge, 1.0 + self.data_bits + parity_n + self.stop_bits - 0.5))

            char = chr(value) if 32 <= value <= 126 else None
            events.append(DecodeEvent(edge, byte_span_end, 'byte',
                                      {'value': value, 'hex': f'0x{value:02X}',
                                       'char': char, 'channel': self.channel}))

            if framing_bad:
                events.append(DecodeEvent(stop_first, byte_span_end, 'framing_error',
                                          {'value': value,
                                           'expected_idle': self.idle}))
            # 游标推进点：定位到停止位「中点」，而不是整个帧的结束边界。
            # 原因：帧尾边界经 round() 后可能比下一个起始沿晚 1 个样本
            # （9600@1MHz 时观察：算得 3230，真实起点却是 3229），
            # 那样会把紧邻的下一个真起始沿误跳过。停止位中点固定在起始沿之后
            # 10 位处，严格落在两帧之间的空闲区，安全且不会漂移。
            cursor = byte_span_end

        return events


def decode_uart(data: bytes, rate: int, channel: int, baud: int,
                **opts: object) -> list[DecodeEvent]:
    """模块级便捷函数：一步完成 UART 解码。"""
    return UartDecoder(SampleStream(data, rate), channel=channel, baud=baud,
                       **opts).decode()
