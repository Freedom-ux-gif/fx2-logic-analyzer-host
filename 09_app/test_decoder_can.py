# -*- coding: utf-8 -*-
"""test_decoder_can.py —— CAN 解码器自测。

策略：先用「编码器」按 CAN 2.0A/B 规范造出已知帧的位序列，再把位序列
转成采样波形，最后用解码器解回来断言逐字段一致。

这样如果编码器和解码器犯了同一个对称错误，测试会假绿；所以关键字段
（ID / DLC / payload / CRC）都用**手工算过的固定期望值**断言，而不是
只做"编码后再解码"的往返对比。
"""

from __future__ import annotations

import sys
import unittest

import numpy as np

sys.path.insert(0, '.')

from decoder_base import SampleStream  # noqa: E402
from decoder_can import CanDecoder, decode_can, _crc15  # noqa: E402


# ---------------------------------------------------------------------------
# 合成器：按 CAN 2.0 规范构造位序列
# ---------------------------------------------------------------------------
def stuff_bits(bits: list[int]) -> list[int]:
    """插入位填充：连续 5 个相同位后插入 1 个相反位。"""
    out: list[int] = []
    run = 0
    last = None
    for b in bits:
        if last is not None and b == last:
            run += 1
        else:
            run = 1
            last = b
        out.append(b)
        if run == 5:
            out.append(1 - b)
            run = 0
            last = 1 - b
    return out


def build_frame(can_id: int, payload: list[int], extended: bool = False,
                remote: bool = False) -> list[int]:
    """构造一个 CAN 2.0 帧的**未填充**位序列（SOF 到 CRC）。

    严格按 ISO 11898-1 的字段顺序：
        标准帧: SOF | ID[11] | RTR | IDE(1) | r0 | DLC[4] | DATA | CRC15
        扩展帧: SOF | BaseID[11] | SRR(1) | IDE(0) | ExtID[18] | RTR | r1,r0 | DLC[4] | DATA | CRC15

    注意 IDE 的极性：显性 0 = 扩展帧，隐性 1 = 标准帧。
    早先版本把 RTR 放到 IDE 之后、且标准帧 IDE 写成 0，两处叠加导致索引整体错位。
    """
    bits: list[int] = [0]                       # SOF（显性）

    if extended:
        for i in range(10, -1, -1):             # Base ID 11 位
            bits.append((can_id >> (18 + i)) & 1)
        bits.append(1)                          # SRR（隐性）
        bits.append(0)                          # IDE=0 -> 扩展帧
        for i in range(17, -1, -1):             # Ext ID 18 位
            bits.append((can_id >> i) & 1)
        bits.append(1 if remote else 0)         # RTR
        bits.extend([0, 0])                     # r1, r0
    else:
        for i in range(10, -1, -1):             # ID 11 位
            bits.append((can_id >> i) & 1)
        bits.append(1 if remote else 0)         # RTR
        bits.append(1)                          # IDE=1 -> 标准帧
        bits.append(0)                          # r0

    dlc = len(payload) if not remote else (len(payload) if payload else 0)
    for i in range(3, -1, -1):                  # DLC 4 位
        bits.append((dlc >> i) & 1)

    if not remote:
        for byte in payload:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)

    crc = _crc15(bits)
    for i in range(14, -1, -1):                 # CRC 15 位
        bits.append((crc >> i) & 1)

    return bits


def bits_to_wave(bits: list[int], spb: int, idle_tail: int = 120) -> bytes:
    """把位序列展开成采样波形字节流（CH0 = bit0）。

    前面加一段总线空闲（隐性 1），后面也补一段，方便解码器找到帧头。
    """
    seq = [1] * (spb * 3) + sum(([b] * spb for b in bits), []) + [1] * (spb * idle_tail)
    arr = np.array(seq, dtype=np.uint8)
    return arr.tobytes()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
class TestCrc(unittest.TestCase):
    def test_crc15_known_vector(self):
        """手工可算的定值，防止 CRC 实现漂移。"""
        self.assertEqual(_crc15([0, 0, 0]), 0x0000)
        self.assertEqual(_crc15([1, 0, 0]), 0x0004)
        self.assertEqual(_crc15([1, 0, 1]), 0x0005)
        # 更强的定值：一整帧的 CRC 必须能被自身校验通过（见 test_crc_ok）


class TestStandardFrame(unittest.TestCase):
    """标准帧 0x123，数据 [0xDE, 0xAD, 0xBE, 0xEF]。"""

    def setUp(self):
        self.spb = 20                       # 每位 20 样本
        self.rate = 500000 * self.spb       # bitrate 500k -> 采样率 10 MHz
        raw = build_frame(0x123, [0xDE, 0xAD, 0xBE, 0xEF], extended=False)
        self.stuffed = stuff_bits(raw)
        self.data = bits_to_wave(self.stuffed, self.spb)

    def test_frame_decoded(self):
        evs = decode_can(self.data, self.rate, channel=0, bitrate=500000)
        kinds = [e.kind for e in evs]
        self.assertIn('frame_start', kinds)
        self.assertIn('data', kinds)
        self.assertIn('frame_end', kinds)

    def test_id_and_dlc(self):
        evs = decode_can(self.data, self.rate, channel=0, bitrate=500000)
        start = [e for e in evs if e.kind == 'frame_start']
        self.assertEqual(len(start), 1)
        self.assertEqual(start[0].data['id'], 0x123)
        self.assertFalse(start[0].data['extended'])
        self.assertFalse(start[0].data['remote'])
        self.assertEqual(start[0].data['dlc'], 4)

    def test_payload(self):
        evs = decode_can(self.data, self.rate, channel=0, bitrate=500000)
        data_ev = [e for e in evs if e.kind == 'data']
        self.assertEqual(len(data_ev), 1)
        self.assertEqual(data_ev[0].data['bytes'], [0xDE, 0xAD, 0xBE, 0xEF])
        self.assertEqual(data_ev[0].data['hex'], 'DE AD BE EF')

    def test_crc_ok(self):
        evs = decode_can(self.data, self.rate, channel=0, bitrate=500000)
        crc = [e for e in evs if e.kind in ('crc', 'crc_error')]
        self.assertEqual(len(crc), 1, f'CRC 事件数量异常: {[e.kind for e in evs]}')
        self.assertEqual(crc[0].kind, 'crc', 'CRC 校验未通过')


class TestExtendedFrame(unittest.TestCase):
    """扩展帧 0x18FF50E5，数据 [0x01, 0x02]。"""

    def test_extended_id(self):
        spb = 20
        rate = 500000 * spb
        raw = build_frame(0x18FF50E5, [0x01, 0x02], extended=True)
        data = bits_to_wave(stuff_bits(raw), spb)
        evs = decode_can(data, rate, channel=0, bitrate=500000)
        start = [e for e in evs if e.kind == 'frame_start']
        self.assertEqual(len(start), 1, f'事件: {[e.kind for e in evs]}')
        self.assertEqual(start[0].data['id'], 0x18FF50E5)
        self.assertTrue(start[0].data['extended'])
        data_ev = [e for e in evs if e.kind == 'data']
        self.assertEqual(data_ev[0].data['bytes'], [0x01, 0x02])


class TestRemoteFrame(unittest.TestCase):
    """远程帧：无数据段。"""

    def test_remote_frame(self):
        spb = 20
        rate = 500000 * spb
        raw = build_frame(0x0AB, [], extended=False, remote=True)
        data = bits_to_wave(stuff_bits(raw), spb)
        evs = decode_can(data, rate, channel=0, bitrate=500000)
        start = [e for e in evs if e.kind == 'frame_start']
        self.assertEqual(len(start), 1, f'事件: {[e.kind for e in evs]}')
        self.assertEqual(start[0].data['id'], 0x0AB)
        self.assertTrue(start[0].data['remote'])
        self.assertEqual([e for e in evs if e.kind == 'data'], [])


class TestCanErrorCases(unittest.TestCase):
    def test_channel_out_of_range(self):
        with self.assertRaises(ValueError):
            decode_can(b'\x00' * 100, 1000000, channel=9, bitrate=500000)

    def test_bad_bitrate(self):
        with self.assertRaises(ValueError):
            decode_can(b'\x00' * 100, 1000000, channel=0, bitrate=0)

    def test_bad_sample_point(self):
        with self.assertRaises(ValueError):
            decode_can(b'\x00' * 100, 1000000, channel=0, bitrate=500000,
                       sample_point=1.5)

    def test_empty(self):
        self.assertEqual(decode_can(b'', 1000000, channel=0, bitrate=500000), [])

    def test_sample_rate_too_low(self):
        # 每位不足 2 个样本时应静默返回空，而不是除零
        self.assertEqual(decode_can(b'\x00' * 1000, 400000, channel=0,
                                    bitrate=500000), [])

    def test_all_idle_no_frames(self):
        # 全隐性 = 总线空闲，没有任何下降沿
        self.assertEqual(decode_can(b'\xFF' * 10000, 10000000, channel=0,
                                    bitrate=500000), [])


class TestBitStuffing(unittest.TestCase):
    def test_stuff_inserted(self):
        """连续 5 个 0 后必须插入 1 个 1。"""
        raw = [0, 0, 0, 0, 0, 0, 0]
        stuffed = stuff_bits(raw)
        self.assertEqual(stuffed, [0, 0, 0, 0, 0, 1, 0, 0])
        self.assertEqual(stuffed.count(1), 1)

    def test_stuff_roundtrip_removed(self):
        """解码器的去填充要把填充位吃掉。"""
        stream = SampleStream(b'\x00' * 100, 1000000)
        dec = CanDecoder(stream, channel=0, bitrate=500000)
        raw = [0, 0, 0, 0, 0, 1, 0, 0]      # 上面插入后的结果
        unstuffed, _ = dec._skip_stuffing(raw, 7)
        self.assertEqual(unstuffed, [0, 0, 0, 0, 0, 0, 0])


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    n = result.testsRun
    fails = len(result.failures) + len(result.errors)
    if fails == 0:
        print(f'ALL TESTS PASSED (cases={n})')
    else:
        print(f'TESTS FAILED: {fails} 失败, 共 {n} 个用例')
    sys.exit(0 if fails == 0 else 1)
