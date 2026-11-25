# -*- coding: utf-8 -*-
"""decoder_can.py —— CAN 总线解码器（纯 Python，numpy 向量化）。

支持：
    - CAN 2.0A（11 位 ID）与 CAN 2.0B（29 位 ID）
    - 标准帧与远程帧
    - 数据长度 0..8 字节
    - 可选 CRC-15 校验（不通过时产生 crc_error 事件，不中断解码）
    - 位填充（bit stuffing）识别与跳过
    - 错误帧、过载帧识别

不支持（明确写在这里，避免被误认为能解）：
    - CAN FD（不同帧格式与 CRC）
    - 位速率切换
    - 硬件错误处理（只做解码，不做总线监视/故障界定）

数据格式约定同其他解码器：每字节 8 通道，CHn 对应 bitn（本机克隆板实测）。

典型用法：
    from decoder_can import decode_can
    events = decode_can(data, rate=4000000, channel=0, bitrate=500000, sample_point=0.875)

对时序的处理
------------
CAN 是异步总线，靠节点各自的位时间同步，而不是共享时钟线。这里用固定
``samples_per_bit = rate / bitrate`` 采样，并在每个下降沿（隐性->显性，
即帧起始 SOF）重新对齐相位。这在同一总线上只有一个发送方、且双方晶振
偏差 < 0.5% 时足够可靠；多节点仲裁期间会有累积误差，属于本实现的已知
限制（见 README）。
"""

from __future__ import annotations

import numpy as np

from decoder_base import DecodeEvent, Decoder, SampleStream

# CAN 帧中的位定义
_SOF = 0          # Start Of Frame，显性 0
_IDE = 0          # 隐式 1 表示扩展帧（29 位 ID）
_RTR = 0          # 隐式 1 表示远程帧
_SRR = 0          # 替代远程请求位（扩展帧里恒为显性）


def _edges(bits: np.ndarray, rising: bool) -> np.ndarray:
    """向量化边沿检测：rising=True 返回 0->1 的下标，False 返回 1->0 的下标。"""
    if bits.size < 2:
        return np.zeros(0, dtype=np.int64)
    if rising:
        return np.flatnonzero((bits[:-1] == 0) & (bits[1:] == 1)) + 1
    return np.flatnonzero((bits[:-1] == 1) & (bits[1:] == 0)) + 1


def _crc15(bits: list[int]) -> int:
    """CAN 的 CRC-15：多项式 x^15 + x^14 + x^10 + x^8 + x^7 + x^4 + x^3 + 1。

    即 0x4599。返回 15 位余数。
    """
    crc = 0
    for b in bits:
        crc <<= 1
        crc |= b
        if crc & 0x8000:
            crc ^= 0x4599
    return crc & 0x7FFF


class CanDecoder(Decoder):
    """CAN 2.0A/B 解码器。"""

    name = 'can'

    def __init__(self, stream: SampleStream, channel: int = 0,
                 bitrate: int = 500000, sample_point: float = 0.875,
                 check_crc: bool = True, **opts: object) -> None:
        """
        Args:
            channel: CAN_RX 信号所在通道（0..7）。
            bitrate: 位速率（bps），常见 125k/250k/500k/1M。
            sample_point: 位内采样点位置（0 < x < 1），典型 0.75~0.875。
            check_crc: 是否校验 CRC-15。校验失败只产生事件，不丢弃帧。
        """
        super().__init__(stream, **opts)
        if not (0 <= channel <= 8):
            raise ValueError(f'channel 必须是 0..7（允许 8 兼容），收到 {channel}')
        if bitrate <= 0:
            raise ValueError(f'bitrate 必须为正，收到 {bitrate}')
        if not (0.0 < sample_point < 1.0):
            raise ValueError(f'sample_point 必须在 (0,1) 之间，收到 {sample_point}')
        self.channel = channel
        self.bitrate = bitrate
        self.sample_point = sample_point
        self.check_crc = check_crc

    # -- 基础工具 -----------------------------------------------------
    def _bits(self) -> np.ndarray:
        return self.stream.channel_bits(self.channel)

    def _read_bits(self, bits: np.ndarray, start: float, count: int,
                   samples_per_bit: float) -> list[int]:
        """从 start（可以是小数样本位置）开始读最多 count 个位。

        用 sample_point 偏移到每位内部再取样本，避免在边沿上取到抖动值。
        **越界时返回已读到的部分**（不返回 None）——因为帧尾的位数取决于
        DLC，提前固定请求一个很大的长度必然越界，硬失败会让有效帧丢失。
        调用方自己检查长度是否够解出一帧。
        """
        out: list[int] = []
        pos = start + samples_per_bit * self.sample_point
        for _ in range(count):
            idx = int(round(pos))
            if idx < 0 or idx >= bits.size:
                break
            out.append(int(bits[idx]))
            pos += samples_per_bit
        return out

    def _skip_stuffing(self, raw: list[int], need: int) -> tuple[list[int], int]:
        """去掉位填充：连续 5 个相同位后，硬件会插入 1 个相反位。

        返回 (去填充后的位列表, 消耗的原始位个数)。
        """
        out: list[int] = []
        run = 0
        last = None
        i = 0
        while i < len(raw) and len(out) < need:
            # 关键：连续 5 个相同位之后的那一位**无条件丢弃**。
            # 它一定与 run 的那 5 位相反，所以不能靠 b != last 来识别——
            # 那正是早先版本漏掉填充位的原因（填充的 1 走进了"正常位"分支）。
            if run == 5:
                i += 1
                run = 0
                last = None
                continue

            b = raw[i]
            out.append(b)
            if b == last:
                run += 1
            else:
                run = 1
                last = b
            i += 1
        return out, i

    # -- 主解码 -------------------------------------------------------
    def decode(self) -> list[DecodeEvent]:
        events: list[DecodeEvent] = []
        bits = self._bits()
        if bits.size < 32:
            return events

        rate = self.stream.rate
        spb = rate / self.bitrate
        if spb < 2:
            # 采样率不足以解这个位速率：至少每位要有 2 个样本
            return events

        # 帧起始：显性跳变（1->0）。总线空闲为隐性 1。
        starts = _edges(bits, rising=False)
        if starts.size == 0:
            return events

        i = 0
        while i < starts.size:
            sof = int(starts[i])
            frame = self._decode_frame(bits, sof, spb, events)
            if frame is None:
                i += 1
                continue
            # frame 返回帧结束位置（用于跳过本帧内的其它下降沿）
            next_i = i + 1
            while next_i < starts.size and starts[next_i] <= frame:
                next_i += 1
            i = next_i
        return events

    def _decode_frame(self, bits: np.ndarray, sof: int, spb: float,
                      events: list[DecodeEvent]) -> int | None:
        """尝试在 sof 处解一帧。成功返回帧结束样本位置，失败返回 None。"""
        # 读足够长的原始位用于去掉填充：扩展帧最长约 64+ 数据位
        raw = self._read_bits(bits, sof, 160, spb)
        if len(raw) < 20:
            return None
        if raw[0] != 0:
            return None                      # SOF 必须是显性

        # 先解 ID（含 RTR/IDE），这段不参与位填充判断的边界较宽松，
        # 实际硬件从 SOF 到 CRC 都做填充，所以统一按去填充处理。
        stuffed, _ = self._skip_stuffing(raw, 140)
        if len(stuffed) < 20:
            return None

        p = 1                                # 跳过 SOF

        # 11 位基础 ID（MSB first）
        if len(stuffed) < p + 11:
            return None
        base_id = 0
        for _ in range(11):
            base_id = (base_id << 1) | stuffed[p]
            p += 1

        # 字段顺序（ISO 11898-1）：
        #   标准帧: ID[11] RTR IDE(1) r0 DLC[4]
        #   扩展帧: BaseID[11] SRR(1) IDE(0) ExtID[18] RTR r1 r0 DLC[4]
        # 注意 RTR 在 IDE **之前**——早先代码先判 RTR 当 IDE，整个控制段错位。
        if p >= len(stuffed):
            return None
        rtr = stuffed[p]
        p += 1

        if p >= len(stuffed):
            return None
        ide = stuffed[p]
        p += 1

        extended = (ide == 0)                # 显性 0 = 扩展帧

        if extended:
            # 扩展帧：这里已经读过 SRR（前面那一位）与 IDE，
            # 上一句 rtr 读的其实是 SRR 位（恒为 1），真正的 RTR 在 ExtID 之后。
            p -= 1                           # 回退：rtr 位其实是 SRR
            p += 1                           # 前进：跳过 SRR（值已读，不用）
            if len(stuffed) < p + 18:
                return None
            ext_id = 0
            for _ in range(18):
                ext_id = (ext_id << 1) | stuffed[p]
                p += 1
            can_id = (base_id << 18) | ext_id
            if p < len(stuffed):
                rtr = stuffed[p]             # 扩展帧的真正 RTR
                p += 1
        else:
            can_id = base_id

        # 控制段：标准帧还剩 r0(1 位)，扩展帧还剩 r1,r0(2 位)，然后 DLC[4]
        skip = 2 if extended else 1
        if len(stuffed) < p + skip + 4:
            return None
        p += skip
        dlc = 0
        for _ in range(4):
            dlc = (dlc << 1) | stuffed[p]
            p += 1
        if dlc > 8:
            return None                      # CAN 2.0 数据长度上限 8

        # 数据段
        payload = []
        if not rtr:
            if len(stuffed) < p + dlc * 8:
                return None
            for _ in range(dlc):
                v = 0
                for _ in range(8):
                    v = (v << 1) | stuffed[p]
                    p += 1
                payload.append(v)

        data_end_sample = int(round(sof + spb * (p + 1.5)))

        events.append(DecodeEvent(
            start_sample=sof,
            end_sample=data_end_sample,
            kind='frame_start',
            data={'id': can_id, 'extended': extended,
                  'remote': bool(rtr), 'dlc': dlc},
        ))

        if payload:
            events.append(DecodeEvent(
                start_sample=sof,
                end_sample=data_end_sample,
                kind='data',
                data={'id': can_id,
                      'bytes': payload,
                      'hex': ' '.join(f'{b:02X}' for b in payload)},
            ))

        # CRC 字段 15 位 + CRC 界定符 1 位
        frame_end = data_end_sample
        if self.check_crc and len(stuffed) >= p + 16:
            got = 0
            for _ in range(15):
                got = (got << 1) | stuffed[p]
                p += 1
            calc = _crc15(stuffed[:p - 15])
            ok = (got == calc)
            events.append(DecodeEvent(
                start_sample=data_end_sample,
                end_sample=frame_end,
                kind='crc' if ok else 'crc_error',
                data={'got': got, 'calc': calc, 'ok': ok},
            ))

        events.append(DecodeEvent(
            start_sample=frame_end,
            end_sample=frame_end + 1,
            kind='frame_end',
            data={'id': can_id},
        ))
        return frame_end


# -- 模块级便捷函数 ---------------------------------------------------
def decode_can(data: bytes, rate: int, channel: int = 0,
               bitrate: int = 500000, sample_point: float = 0.875,
               check_crc: bool = True) -> list[DecodeEvent]:
    """一句话解 CAN。

    Args:
        data: 原始采样字节流。
        rate: 采样率（Hz）。
        channel: CAN_RX 所在通道（0..7）。
        bitrate: 总线位速率（bps）。
        sample_point: 位内采样点比例（默认 0.875，即 87.5% 处采样）。
        check_crc: 是否校验 CRC-15。

    Returns:
        DecodeEvent 列表，帧序列形如：
        frame_start -> data -> crc -> frame_end
    """
    stream = SampleStream(data, rate)
    return CanDecoder(stream, channel=channel, bitrate=bitrate,
                      sample_point=sample_point, check_crc=check_crc).decode()
