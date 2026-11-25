# -*- coding: utf-8 -*-
"""test_decoders.py —— 纯标准库 unittest 的合成数据自测。

覆盖大脑指定的 5 条硬判据：
    "Hello"@9600 全 5 字节 / "Hi"@115200 全 2 字节 /
    I2C data [1,2] / SPI words [0xAA,0x55] / CH1<->CH2 位序
另覆盖契约要求的 115200 Hello、偶校验、坏帧、I2C 读/Restart、SPI CPHA=1。

运行：python -I test_decoders.py
"""

import os
import sys
import unittest

import numpy as np

# python -I 是隔离模式，sys.path 里没有当前目录；这里显式插入脚本所在目录。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decoder_base  # noqa: E402
import decoder_i2c  # noqa: E402
import decoder_spi  # noqa: E402
import decoder_uart  # noqa: E402
import synth  # noqa: E402


class UartTests(unittest.TestCase):
    """UART 解码器测试。"""

    def test_hello_9600_all_five_bytes(self):
        data = synth.synth_uart('Hello', baud=9600, rate=1000000, channel=1)
        events = decoder_uart.decode_uart(data, 1000000, 1, 9600)
        values = [e.data['value'] for e in events if e.kind == 'byte']
        self.assertEqual(values, [72, 101, 108, 108, 111])

    def test_hi_115200_all_two_bytes(self):
        data = synth.synth_uart('Hi', baud=115200, rate=1000000, channel=1)
        events = decoder_uart.decode_uart(data, 1000000, 1, 115200)
        values = [e.data['value'] for e in events if e.kind == 'byte']
        self.assertEqual(values, [72, 105])

    def test_hello_115200(self):
        data = synth.synth_uart('Hello', baud=115200, rate=1000000, channel=1)
        values = [e.data['value'] for e in decoder_uart.decode_uart(
            data, 1000000, 1, 115200) if e.kind == 'byte']
        self.assertEqual(values, [72, 101, 108, 108, 111])

    def test_even_parity(self):
        data = synth.synth_uart('Hello', 9600, 1000000, 1, parity='even')
        events = decoder_uart.decode_uart(data, 1000000, 1, 9600, parity='even')
        values = [e.data['value'] for e in events if e.kind == 'byte']
        self.assertEqual(values, [72, 101, 108, 108, 111])
        self.assertEqual(sum(1 for e in events if e.kind == 'parity_error'), 0)

    def test_framing_error(self):
        # 造一个缺停止位的坏帧：用 8N1 正常帧但把停止位改成 0。
        data = bytearray(synth.synth_uart('A', 9600, 1000000, 1))
        spb = 1000000 / 9600
        # 合成波形位序：bit0=空闲, bit1=起始, bit2..9=D0..D7, bit10=停止位。
        # 把停止位槽（bit10）全部拉低，使停止位采样落在 0 上。
        stop_a = int(round(10 * spb)) + 2
        stop_b = int(round(11 * spb)) - 2
        for i in range(stop_a, stop_b):
            data[i] &= ~(1 << 1)  # channel=1 对应 bit1（本板 CHn->bitn），强行拉低停止位
        events = decoder_uart.decode_uart(bytes(data), 1000000, 1, 9600)
        self.assertTrue(any(e.kind == 'framing_error' for e in events),
                        f'未产生 framing_error，事件={events}')


class I2cTests(unittest.TestCase):
    """I2C 解码器测试。"""

    def test_write_two_bytes_event_sequence(self):
        data = synth.synth_i2c([{'addr': 0x50, 'rw': 0, 'data': [1, 2]}],
                               1000000, 1, 2, half_period=100)
        events = decoder_i2c.decode_i2c(data, 1000000, 1, 2)
        self.assertEqual([e.kind for e in events],
                         ['start', 'address', 'ack', 'data', 'ack', 'data', 'ack', 'stop'])
        addr = next(e for e in events if e.kind == 'address')
        self.assertEqual(addr.data['addr'], 0x50)
        self.assertEqual(addr.data['rw'], 0)
        self.assertEqual([e.data['value'] for e in events if e.kind == 'data'], [1, 2])

    def test_read_operation(self):
        data = synth.synth_i2c([{'addr': 0x50, 'rw': 1, 'data': [0xAB]}],
                               1000000, 1, 2, half_period=100)
        events = decoder_i2c.decode_i2c(data, 1000000, 1, 2)
        addr = next(e for e in events if e.kind == 'address')
        self.assertEqual(addr.data['addr'], 0x50)
        self.assertEqual(addr.data['rw'], 1)
        self.assertEqual([e.data['value'] for e in events if e.kind == 'data'], [0xAB])

    def test_repeat_start(self):
        # 真正的 Sr 场景：第一笔 no_stop=True 不释放总线，第二笔以重复起始接续。
        data = synth.synth_i2c([{'addr': 0x50, 'rw': 0, 'data': [1], 'no_stop': True},
                                {'addr': 0x50, 'rw': 1, 'data': [2]}],
                               1000000, 1, 2, half_period=100)
        events = decoder_i2c.decode_i2c(data, 1000000, 1, 2)
        kinds = [e.kind for e in events]
        self.assertEqual(kinds.count('start'), 1)
        self.assertEqual(kinds.count('repeat_start'), 1)
        self.assertEqual(kinds.count('stop'), 1)
        self.assertEqual([e.data['value'] for e in events if e.kind == 'data'], [1, 2])

    def test_independent_transactions(self):
        # 两笔之间发 STOP -> 两个独立事务，应各自 start，无 repeat_start。
        data = synth.synth_i2c([{'addr': 0x50, 'rw': 0, 'data': [1]},
                                {'addr': 0x51, 'rw': 0, 'data': [2]}],
                               1000000, 1, 2, half_period=100)
        kinds = [e.kind for e in decoder_i2c.decode_i2c(data, 1000000, 1, 2)]
        self.assertEqual(kinds.count('start'), 2)
        self.assertEqual(kinds.count('repeat_start'), 0)


class SpiTests(unittest.TestCase):
    """SPI 解码器测试。"""

    def test_mode0_words(self):
        data = synth.synth_spi([0xAA, 0x55], 1000000, 1, 2, 3, cpol=0, cpha=0)
        events = decoder_spi.decode_spi(data, 1000000, 1, 2, cs_ch=3, cpol=0, cpha=0)
        words = [e.data['value'] for e in events if e.kind == 'word']
        self.assertEqual(words, [0xAA, 0x55])

    def test_cpha1_words(self):
        data = synth.synth_spi([0xAA, 0x55], 1000000, 1, 2, 3, cpol=0, cpha=1)
        events = decoder_spi.decode_spi(data, 1000000, 1, 2, cs_ch=3, cpol=0, cpha=1)
        words = [e.data['value'] for e in events if e.kind == 'word']
        self.assertEqual(words, [0xAA, 0x55])


class ChannelOrderTests(unittest.TestCase):
    """通道位序测试。"""

    def test_ch0_square_ch1_zero(self):
        # 本机克隆板实测映射：CHn -> bitn（CH0=bit0 ... CH7=bit7）
        data = synth.synth_square_wave(1000, 1000000, 0.01, channel=0)
        stream = decoder_base.SampleStream(data, 1000000)
        ch0 = stream.channel_bits(0)
        ch1 = stream.channel_bits(1)
        self.assertTrue(bool((ch0 == 1).any()) and bool((ch0 == 0).any()),
                        'CH0 应为方波')
        self.assertTrue(bool((ch1 == 0).all()), 'CH1 应全 0')
        # 位序直接验证：CH0 数据应落在 bit0 上
        raw = np.frombuffer(data, dtype=np.uint8)
        self.assertTrue(bool(((raw == 0x00) | (raw == 0x01)).all()),
                        f'CH0 方波应只产生 0x00/0x01，实际 {sorted(set(raw.tolist()))[:5]}')
        with self.assertRaises(ValueError):
            stream.channel_bits(-1)
        with self.assertRaises(ValueError):
            stream.channel_bits(9)


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    count = result.testsRun
    if result.wasSuccessful():
        print(f'ALL TESTS PASSED (cases={count})')
        sys.exit(0)
    print(f'TESTS FAILED (cases={count}, failures={len(result.failures)}, '
          f'errors={len(result.errors)})')
    sys.exit(1)
