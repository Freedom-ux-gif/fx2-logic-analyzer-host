# -*- coding: utf-8 -*-
"""decoder_spi.py —— 纯 Python 的 SPI（同步串行外设接口）解码器。

SPI 模式由 CPOL/CPHA 决定采样边沿：
    - CPOL=0：SCK 空闲为低，第一个边沿是上升沿；
    - CPOL=1：SCK 空闲为高，第一个边沿是下降沿；
    - CPHA=0：在第一个边沿采样；
    - CPHA=1：在第二个边沿采样。
CS（片选）低电平有效；CS 变高即结束一帧。
每 bits 位组成一个 word；若给定 MISO 通道则同时输出 miso_word。

边沿检测同样用 numpy 向量化完成。
"""

from __future__ import annotations

import numpy as np

from decoder_base import DecodeEvent, SampleStream, Decoder


def _edges(bits: np.ndarray, rising: bool) -> np.ndarray:
    """向量化边沿检测：rising=True 返回 0->1，False 返回 1->0 的下标。"""
    if bits.size < 2:
        return np.zeros(0, dtype=np.int64)
    if rising:
        return np.flatnonzero((bits[:-1] == 0) & (bits[1:] == 1)) + 1
    return np.flatnonzero((bits[:-1] == 1) & (bits[1:] == 0)) + 1


class SpiDecoder(Decoder):
    """SPI 解码器。"""

    name = 'spi'

    def __init__(
        self,
        stream: SampleStream,
        sck_channel: int = 1,
        mosi_channel: int = 2,
        miso_channel: int | None = None,
        cs_channel: int | None = None,
        cpol: int = 0,
        cpha: int = 0,
        bits: int = 8,
        msb_first: bool = True,
        **opts: object,
    ) -> None:
        super().__init__(stream, **opts)
        for label, ch in (('sck_channel', sck_channel), ('mosi_channel', mosi_channel)):
            if not (0 <= ch <= 8):
                raise ValueError(f'{label} 必须是 0..7（允许 8 兼容），收到 {ch}')
        if cs_channel is not None and not (0 <= cs_channel <= 8):
            raise ValueError(f'cs_channel 必须是 0..7 或 None，收到 {cs_channel}')
        if miso_channel is not None and not (0 <= miso_channel <= 8):
            raise ValueError(f'miso_channel 必须是 0..7 或 None，收到 {miso_channel}')
        if cpol not in (0, 1) or cpha not in (0, 1):
            raise ValueError('cpol/cpha 只能是 0 或 1')
        if not (1 <= bits <= 32):
            raise ValueError(f'bits 必须在 1..32，收到 {bits}')
        self.sck_ch = sck_channel
        self.mosi_ch = mosi_channel
        self.miso_ch = miso_channel
        self.cs_ch = cs_channel
        self.cpol = cpol
        self.cpha = cpha
        self.bits = bits
        self.msb_first = msb_first

    def decode(self) -> list[DecodeEvent]:
        """解码整段 SPI 波形，返回事件列表。"""
        n = self.stream.n_samples
        events: list[DecodeEvent] = []
        if n < 2:
            return events

        sck = self.stream.channel_bits(self.sck_ch)
        mosi = self.stream.channel_bits(self.mosi_ch)
        miso = (self.stream.channel_bits(self.miso_ch)
                if self.miso_ch is not None else None)
        cs = (self.stream.channel_bits(self.cs_ch)
              if self.cs_ch is not None else None)

        # CPHA=0 采样第一个边沿：CPOL=0 时是上升沿，CPOL=1 时是下降沿。
        # CPHA=1 采样第二个边沿：取与第一个相反的边沿。
        first_rising = (self.cpol == 0)
        sample_rising = first_rising if self.cpha == 0 else (not first_rising)
        sample_edges = [int(i) for i in _edges(sck, rising=sample_rising)]

        # 帧区间：给出 CS 时按 CS 低电平分段；否则整段算一帧。
        if cs is not None:
            cs_fall = [int(i) for i in _edges(cs, rising=False)]
            cs_rise = [int(i) for i in _edges(cs, rising=True)]
            frames: list[tuple[int, int]] = []
            for f in cs_fall:
                end = next((r for r in cs_rise if r > f), n)
                frames.append((f, end))
        else:
            frames = [(0, n)]

        def assemble(edge_list: list[int], line: np.ndarray) -> int:
            """把一组采样边沿处的电平组装成一个 word。"""
            value = 0
            for pos, edge in enumerate(edge_list):
                bit = int(line[edge]) if edge < n else 0
                if self.msb_first:
                    value = (value << 1) | bit
                else:
                    value |= bit << pos
            return value

        for f_start, f_end in frames:
            events.append(DecodeEvent(f_start, f_start + 1, 'cs_assert',
                                      {'channel': self.cs_ch}))
            frame_edges = [e for e in sample_edges if f_start <= e < f_end]
            # 每 bits 个采样边沿组成一个 word。
            for word_i in range(0, len(frame_edges), self.bits):
                chunk = frame_edges[word_i:word_i + self.bits]
                if len(chunk) < self.bits:
                    break  # 不足一个完整 word，丢弃残位
                value = assemble(chunk, mosi)
                info: dict[str, object] = {
                    'value': value, 'hex': f'0x{value:0{self.bits // 4 or 1}X}',
                    'index': word_i // self.bits,
                }
                if miso is not None:
                    info['miso_word'] = assemble(chunk, miso)
                events.append(DecodeEvent(chunk[0], chunk[-1] + 1, 'word', info))
            events.append(DecodeEvent(f_end, f_end + 1, 'cs_deassert',
                                      {'channel': self.cs_ch}))
            events.append(DecodeEvent(f_start, f_end, 'frame',
                                      {'bit_count': len(frame_edges)}))

        return events


def decode_spi(
    data: bytes,
    rate: int,
    sck_ch: int,
    mosi_ch: int,
    miso_ch: int | None = None,
    cs_ch: int | None = None,
    cpol: int = 0,
    cpha: int = 0,
    bits: int = 8,
    msb_first: bool = True,
) -> list[DecodeEvent]:
    """模块级便捷函数：一步完成 SPI 解码。"""
    return SpiDecoder(
        SampleStream(data, rate), sck_channel=sck_ch, mosi_channel=mosi_ch,
        miso_channel=miso_ch, cs_channel=cs_ch, cpol=cpol, cpha=cpha,
        bits=bits, msb_first=msb_first,
    ).decode()
