# -*- coding: utf-8 -*-
"""synth.py —— 合成测试数据生成器（本任务的验证基础）。

能根据"已知内容"生成对应的数字波形字节流，用于反证解码器的正确性。
所有合成器都通过 pack_channels() 统一打包，确保通道位序一致：
    CHn -> bitn（本机克隆板实测：CH0=bit0 … CH7=bit7）。
    为兼容旧的 1..8 编号，ch=8 映射到 bit7。
"""

from __future__ import annotations

import numpy as np


def pack_channels(channels: dict[int, np.ndarray]) -> bytes:
    """把 若干通道的电平数组 打包成 Saleae 原始字节流。

    channels: {通道号: 0/1 数组}，长度必须一致；未给出的通道恒为 0。
    CH1 放 bit7，CH8 放 bit0。
    """
    if not channels:
        raise ValueError('channels 不能为空')
    lengths = {len(v) for v in channels.values()}
    if len(lengths) != 1:
        raise ValueError(f'所有通道长度必须一致，收到 {lengths}')
    n = lengths.pop()
    packed = np.zeros(n, dtype=np.uint8)
    for ch, arr in channels.items():
        if not (0 <= ch <= 8):
            raise ValueError(f'通道号必须是 0..7（允许 8 兼容旧代码），收到 {ch}')
        bit = 7 if ch == 8 else ch         # 兼容旧编号
        a = np.asarray(arr, dtype=np.uint8)
        if a.size != n:
            raise ValueError(f'通道 {ch} 长度 {a.size} 与预期 {n} 不符')
        packed |= (a & 1) << bit           # 唯一的位序转换点：CHn -> bitn
    return packed.tobytes()


def _tile_bits(levels: list[int], spb: float) -> np.ndarray:
    """把每个电平按 samples_per_bit 个样本展开（四舍五入每个边界）。"""
    edges = np.round(np.arange(len(levels) + 1) * spb).astype(int)
    out = np.empty(edges[-1], dtype=np.uint8)
    for i, lev in enumerate(levels):
        out[edges[i]:edges[i + 1]] = lev
    return out


def synth_uart(
    text: str,
    baud: int,
    rate: int,
    channel: int = 1,
    idle_high: bool = True,
    data_bits: int = 8,
    parity: str = 'none',
    stop_bits: int = 1,
    **_: object,
) -> bytes:
    """生成含指定文本的 UART 波形，返回 8 通道打包后的字节流。"""
    if baud <= 0 or rate <= 0:
        raise ValueError('baud/rate 必须为正')
    idle = 1 if idle_high else 0
    mark = 0 if idle_high else 1
    spb = rate / baud
    levels: list[int] = [idle]                       # 1 位空闲起始
    for ch in text:
        val = ord(ch)
        if val >= 1 << data_bits:
            raise ValueError(f'字符 {ch!r} 超出 {data_bits} 位')
        levels.append(mark)                          # 起始位
        for k in range(data_bits):                   # LSB first
            levels.append((val >> k) & 1)
        if parity != 'none':
            ones = bin(val).count('1')
            if parity == 'even':
                levels.append(ones % 2)
            elif parity == 'odd':
                levels.append((ones + 1) % 2)
            else:
                raise ValueError(f'未知校验 {parity}')
        levels.extend([idle] * stop_bits)            # 停止位
    levels.append(idle)                              # 结尾留 1 位空闲
    bits = _tile_bits(levels, spb)
    return pack_channels({channel: bits})


def synth_i2c(transactions: list[dict], rate: int, scl_ch: int = 1,
              sda_ch: int = 2, half_period: int | None = None) -> bytes:
    """生成 I2C 波形。transactions 形如 [{'addr':0x50,'rw':0,'data':[0x01,0x02]}]。

    在 transaction dict 里加 'no_stop': True 表示该笔之后不释放总线，
    下一笔以重复起始(Sr)接续（典型场景：写完地址后不改地址直接切读方向）。

    实现以"相位"为单位：每相位 hp 个样本，SCL 的每个 0->1 上升沿严格对应一位。
    """
    if rate <= 0:
        raise ValueError('rate 必须为正')
    hp = half_period if half_period is not None else max(1, rate // 100000)
    if hp < 2:
        raise ValueError('half_period 至少为 2')

    scl: list[int] = [1] * hp
    sda: list[int] = [1] * hp

    def phase(scl_level: int, sda_level: int) -> None:
        """追加一个 SCL/SDA 相位（各 hp 个样本）。"""
        scl.extend([scl_level] * hp)
        sda.extend([sda_level] * hp)

    def start_cond(repeat: bool = False) -> None:
        # START/Sr：SCL 高时 SDA 由 1 变 0。
        # 普通 START 前 SDA 处于空闲高电平；Sr 前 SDA 由上一字节的 ACK 拉高。
        if not repeat:
            phase(1, 1)
        phase(1, 0)

    def stop_cond() -> None:
        # STOP：SCL 高时 SDA 由 0 变 1。
        phase(1, 0)
        phase(1, 1)

    def put_byte(val: int, last_ack_high: bool = False) -> None:
        # 8 位，MSB first；每位先建数据(SCL=0)，再给一个上升沿(SCL=1)。
        for k in range(7, -1, -1):
            bit = (val >> k) & 1
            phase(0, bit)
            phase(1, bit)
        # 第 9 个时钟：ACK(SDA=0)；last_ack_high=True 时用 NACK(SDA=1)
        # 为紧随其后的 Sr 预置 SDA 高电平。
        ack_bit = 1 if last_ack_high else 0
        phase(0, ack_bit)
        phase(1, ack_bit)

    for i, tx in enumerate(transactions):
        # 上一笔声明 no_stop 时，本笔以 Sr 接续（SDA 已被预置为高）。
        repeat = i > 0 and transactions[i - 1].get('no_stop', False)
        start_cond(repeat=repeat)
        addr = ((tx['addr'] & 0x7F) << 1) | (tx['rw'] & 1)
        data = tx.get('data', [])
        for j, val in enumerate([addr] + [b & 0xFF for b in data]):
            # 若本笔之后要接续 Sr，则最后一个 ACK 字节需把 SDA 预置为高。
            put_byte(val, last_ack_high=(tx.get('no_stop', False)
                                         and j == len(data)))
        if not tx.get('no_stop', False):
            stop_cond()
    # 收尾空闲。
    phase(1, 1)
    phase(1, 1)
    return pack_channels({scl_ch: np.array(scl, dtype=np.uint8),
                          sda_ch: np.array(sda, dtype=np.uint8)})


def synth_spi(
    words: list[int],
    rate: int,
    sck_ch: int = 1,
    mosi_ch: int = 2,
    cs_ch: int = 3,
    cpol: int = 0,
    cpha: int = 0,
    bits: int = 8,
    msb_first: bool = True,
    miso_ch: int | None = None,
    miso_words: list[int] | None = None,
    half_period: int | None = None,
) -> bytes:
    """生成 SPI 波形，返回打包字节流。

    用统一的"相位列表"构造，每个相位 hp 个样本，相位元组为
    (SCK电平, MOSI电平, MISO电平, CS电平)，避免多个数组分头 extend 漏项。

    CPHA 语义（关键）：
      - CPHA=0：数据在第一个边沿之前就稳定，采样在第一个边沿；
                phase1 与 phase2 都输出当前 bit。
      - CPHA=1：数据在第一个边沿才切换，采样在第二个边沿；
                phase1 输出"上一个 bit"，phase2 输出当前 bit。
    CS 在整个数据阶段保持低电平，帧末拉高。
    """
    if rate <= 0:
        raise ValueError('rate 必须为正')
    if cpol not in (0, 1) or cpha not in (0, 1):
        raise ValueError('cpol/cpha 只能是 0 或 1')
    if not (1 <= bits <= 32):
        raise ValueError('bits 必须在 1..32')
    hp = half_period if half_period is not None else max(1, rate // 1000000)

    # 先把所有 word 展开成 bit 序列（MSB/LSB 顺序由 msb_first 决定）。
    bit_values: list[int] = []
    miso_values: list[int] = []
    for wi, word in enumerate(words):
        order = range(bits - 1, -1, -1) if msb_first else range(bits)
        bit_values.extend((word >> k) & 1 for k in order)
        mw = (miso_words[wi] if miso_words is not None and wi < len(miso_words) else 0)
        miso_values.extend((mw >> k) & 1 for k in order)

    # 相位列表：初始空闲(CS高) -> CS拉低 -> 各位 -> 收尾采样相位 -> 帧结束(CS高)。
    segs: list[tuple[int, int, int, int]] = [(cpol, 0, 0, 1), (cpol, 0, 0, 0)]
    prev_mosi, prev_miso = 0, 0
    for bit, mbit in zip(bit_values, miso_values):
        if cpha == 0:
            segs.append((cpol, bit, mbit, 0))
            segs.append((1 - cpol, bit, mbit, 0))
        else:
            # 第一个边沿处数据才切换：phase1 保持旧值，phase2 放新值。
            segs.append((cpol, prev_mosi, prev_miso, 0))
            segs.append((1 - cpol, bit, mbit, 0))
        prev_mosi, prev_miso = bit, mbit
    # 收尾相位：CPHA=1 时最后一个下降沿在此相位起点采样，必须保持最后一位。
    segs.append((cpol, prev_mosi, prev_miso, 0))
    segs.append((cpol, 0, 0, 1))

    sck = np.concatenate([np.full(hp, q[0], dtype=np.uint8) for q in segs])
    mosi = np.concatenate([np.full(hp, q[1], dtype=np.uint8) for q in segs])
    miso = np.concatenate([np.full(hp, q[2], dtype=np.uint8) for q in segs])
    cs = np.concatenate([np.full(hp, q[3], dtype=np.uint8) for q in segs])

    channels = {sck_ch: sck, mosi_ch: mosi, cs_ch: cs}
    if miso_ch is not None:
        channels[miso_ch] = miso
    # 防御式断言：相位列表法天然等长，这里再显式确认一次。
    assert len(set(map(len, channels.values()))) == 1,         f'各通道长度不一致：{ {k: len(v) for k, v in channels.items()} }'
    return pack_channels(channels)


def synth_square_wave(freq: float, rate: int, seconds: float,
                      channel: int = 1, duty: float = 0.5) -> bytes:
    """生成方波（供通道位序验证）。

    用向量化的相位计算：phase = (arange(n)/rate * freq) % 1，小于 duty 为高。
    """
    if rate <= 0 or freq <= 0 or seconds <= 0:
        raise ValueError('rate/freq/seconds 必须为正')
    if not (0 < duty < 1):
        raise ValueError('duty 必须在 (0,1)')
    n = int(round(rate * seconds))
    t = np.arange(n, dtype=np.float64) / rate
    phase = (t * freq) % 1.0
    bits = (phase < duty).astype(np.uint8)
    return pack_channels({channel: bits})
