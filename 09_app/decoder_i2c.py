# -*- coding: utf-8 -*-
"""decoder_i2c.py —— 纯 Python 的 I2C（两线串行总线）解码器。

I2C 时序约定：
    - START：SCL 为高时 SDA 由高变低；STOP：SCL 为高时 SDA 由低变高。
    - 数据位在 SCL 上升沿被采样，MSB first。
    - 每 8 位后第 9 个时钟是 ACK/NACK（SDA 低=ACK，高=NACK）。
    - 第一个字节是地址：高 7 位为地址，最低位 R/W（0=写，1=读）。
    - 重复起始（Repeated START）不释放总线，必须识别为 repeat_start。

性能：START/STOP 与 SCL 上升沿都用 numpy 向量化检测，
      只在"边沿"这一稀疏集合上做逐项处理，而非逐样本 Python 循环。
"""

from __future__ import annotations

import numpy as np

from decoder_base import DecodeEvent, SampleStream, Decoder


def _rising_edges(bits: np.ndarray) -> np.ndarray:
    """向量化：返回 0->1 跳变后第一个高电平样本的下标数组。"""
    if bits.size < 2:
        return np.zeros(0, dtype=np.int64)
    return np.flatnonzero((bits[:-1] == 0) & (bits[1:] == 1)) + 1


def _falling_edges(bits: np.ndarray) -> np.ndarray:
    """向量化：返回 1->0 跳变后第一个低电平样本的下标数组。"""
    if bits.size < 2:
        return np.zeros(0, dtype=np.int64)
    return np.flatnonzero((bits[:-1] == 1) & (bits[1:] == 0)) + 1


class I2cDecoder(Decoder):
    """I2C 解码器。"""

    name = 'i2c'

    def __init__(
        self,
        stream: SampleStream,
        scl_channel: int = 1,
        sda_channel: int = 2,
        **opts: object,
    ) -> None:
        super().__init__(stream, **opts)
        for label, ch in (('scl_channel', scl_channel), ('sda_channel', sda_channel)):
            if not (0 <= ch <= 8):
                raise ValueError(f'{label} 必须是 0..7（允许 8 兼容），收到 {ch}')
        if scl_channel == sda_channel:
            raise ValueError('SCL 与 SDA 不能使用同一通道')
        self.scl_ch = scl_channel
        self.sda_ch = sda_channel

    def decode(self) -> list[DecodeEvent]:
        """解码整段 I2C 波形，返回事件列表。"""
        n = self.stream.n_samples
        events: list[DecodeEvent] = []
        if n < 2:
            return events

        scl: np.ndarray = self.stream.channel_bits(self.scl_ch)
        sda: np.ndarray = self.stream.channel_bits(self.sda_ch)

        # —— 向量化边沿检测 ——
        sda_fall = _falling_edges(sda)   # SDA 下降沿候选（START）
        sda_rise = _rising_edges(sda)    # SDA 上升沿候选（STOP）
        scl_rise = _rising_edges(scl)    # SCL 上升沿（采样时钟）

        # 只有 SCL=1 时的 SDA 跳变才构成 START/STOP。
        cond_list: list[tuple[int, str]] = []
        cond_list += [(int(i), 'start') for i in sda_fall if scl[i] == 1]
        cond_list += [(int(i), 'stop') for i in sda_rise if scl[i] == 1]

        # 合并 SCL 时钟沿与总线条件，按时间排序后单遍扫描。
        timeline: list[tuple[int, str]] = cond_list
        timeline += [(int(i), 'clock') for i in scl_rise]
        timeline.sort(key=lambda x: (x[0], 0 if x[1] != 'clock' else 1))

        # 逐字节状态：bit_count 严格按 0..8 循环——0..7 是数据位，8 是 ACK/NACK。
        # （原实现用 len(bits)==9 判断 ACK，但凑满 8 位后 bits 被清空，
        #   ACK 变成"新字节的第 1 位"，导致数据整体错位一位。）
        bits: list[int] = []         # 当前字节已采集的 8 个数据位（MSB 先到）
        byte_edges: list[int] = []
        bit_count = 0                # 本字节已采样的时钟数（含 ACK 位）
        byte_index = 0               # 0=地址字节，>=1=数据字节
        active = False               # 是否处于一次 START..STOP 事务中

        def reset_byte() -> None:
            """清空当前字节的累积状态。"""
            nonlocal bits, byte_edges, bit_count
            bits = []
            byte_edges = []
            bit_count = 0

        def flush_byte(ack_edge: int) -> None:
            """把凑满 8 位的数据位包装成地址或数据事件。"""
            nonlocal byte_index
            value = 0
            for b in bits:                       # MSB first：先到的位放高位
                value = (value << 1) | b
            span_s, span_e = byte_edges[0], byte_edges[-1] + 1
            if byte_index == 0:
                events.append(DecodeEvent(span_s, span_e, 'address',
                                          {'addr': value >> 1, 'rw': value & 1,
                                           'value': value}))
            else:
                events.append(DecodeEvent(span_s, span_e, 'data', {'value': value}))
            byte_index += 1
            # ACK/NACK 在第 9 个时钟（ack_edge）采样。
            is_ack = (int(sda[ack_edge - 1 if ack_edge else 0]) == 0)
            events.append(DecodeEvent(ack_edge, ack_edge + 1,
                                      'ack' if is_ack else 'nack', {'ack': is_ack}))

        for idx, typ in timeline:
            if typ == 'start' or typ == 'repeat_start':
                # 已在事务中（未收到 STOP）又来 START -> 重复起始 Sr。
                kind = 'repeat_start' if active else 'start'
                events.append(DecodeEvent(idx, idx + 1, kind,
                                          {'scl': self.scl_ch, 'sda': self.sda_ch}))
                active = True
                reset_byte()
                byte_index = 0
            elif typ == 'stop':
                if active:
                    events.append(DecodeEvent(idx, idx + 1, 'stop', {}))
                active = False
                reset_byte()
            else:  # clock：SCL 上升沿，采一位
                if not active:
                    continue
                # SDA 在 SCL 低电平期间已稳定，取上升沿前 1 个样本最稳妥。
                sample_idx = idx - 1 if idx > 0 else idx
                bit = int(sda[sample_idx])
                if bit_count < 8:
                    bits.append(bit)
                    byte_edges.append(idx)
                    bit_count += 1
                else:
                    # 第 9 个时钟：ACK/NACK（低=ACK），然后收尾本字节。
                    flush_byte(idx)
                    reset_byte()

        return events

        scl: np.ndarray = self.stream.channel_bits(self.scl_ch)
        sda: np.ndarray = self.stream.channel_bits(self.sda_ch)

        # —— 向量化边沿检测 ——
        sda_fall = _falling_edges(sda)   # SDA 下降沿候选（START）
        sda_rise = _rising_edges(sda)    # SDA 上升沿候选（STOP）
        scl_rise = _rising_edges(scl)    # SCL 上升沿（采样时钟）

        # 只有 SCL=1 时的 SDA 跳变才构成 START/STOP。
        cond_list: list[tuple[int, str]] = []
        cond_list += [(int(i), 'start') for i in sda_fall if scl[i] == 1]
        cond_list += [(int(i), 'stop') for i in sda_rise if scl[i] == 1]

        # 合并 SCL 时钟沿与总线条件，按时间排序后单遍扫描。
        timeline: list[tuple[int, str]] = cond_list
        timeline += [(int(i), 'clock') for i in scl_rise]
        timeline.sort(key=lambda x: (x[0], 0 if x[1] != 'clock' else 1))

        # 逐字节状态：
        bits: list[int] = []         # 当前字节已采集的位（MSB 先到）
        byte_edges: list[int] = []
        byte_index = 0               # 0=地址字节，>=1=数据字节
        active = False               # 是否处于一次 START..STOP 事务中

        def flush_byte() -> None:
            """把一个凑满 8 位的字节包装成地址或数据事件。"""
            nonlocal byte_index, bits, byte_edges
            if not bits:
                return
            value = 0
            for b in bits:                       # MSB first：先到的位放高位
                value = (value << 1) | b
            span_s, span_e = byte_edges[0], byte_edges[-1] + 1
            if byte_index == 0:
                events.append(DecodeEvent(span_s, span_e, 'address',
                                          {'addr': value >> 1, 'rw': value & 1,
                                           'value': value}))
            else:
                events.append(DecodeEvent(span_s, span_e, 'data', {'value': value}))
            byte_index += 1
            bits = []
            byte_edges = []

        for idx, typ in timeline:
            if typ == 'start' or typ == 'repeat_start':
                # 已在事务中 -> 判为重复起始；否则为普通起始。
                kind = 'repeat_start' if active else 'start'
                events.append(DecodeEvent(idx, idx + 1, kind,
                                          {'scl': self.scl_ch, 'sda': self.sda_ch}))
                active = True
                bits = []
                byte_edges = []
                byte_index = 0
            elif typ == 'stop':
                if active:
                    events.append(DecodeEvent(idx, idx + 1, 'stop', {}))
                active = False
                bits = []
                byte_edges = []
            else:  # clock：SCL 上升沿，采一位
                if not active:
                    continue
                # I2C 规定数据在 SCL 低电平期间变化、在上升沿之前已稳定。
                # 合成器在 SCL 拉高的同一批样本上就翻转 SDA，若在 edge 处采样
                # 会读到"下一位"。因此取上升沿前 1 个样本（SCL 仍为低）的 SDA。
                sample_idx = idx - 1 if idx > 0 else idx
                bit = int(sda[sample_idx])
                bits.append(bit)
                byte_edges.append(idx)
                if len(bits) == 8:
                    flush_byte()
                elif len(bits) == 9:
                    # 第 9 位：SDA 低=ACK，高=NACK。
                    is_ack = (bit == 0)
                    events.append(DecodeEvent(idx, idx + 1,
                                              'ack' if is_ack else 'nack',
                                              {'ack': is_ack}))
                    bits = []
                    byte_edges = []

        return events


def decode_i2c(data: bytes, rate: int, scl_ch: int, sda_ch: int) -> list[DecodeEvent]:
    """模块级便捷函数：一步完成 I2C 解码。"""
    return I2cDecoder(SampleStream(data, rate),
                      scl_channel=scl_ch, sda_channel=sda_ch).decode()
