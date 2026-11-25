# -*- coding: utf-8 -*-
"""合成数据自测：导出功能 + 像素级降采样正确性 + 性能。

运行：python -I test_view_export.py
全部使用合成数据，不依赖真实设备、不依赖另一个执行手的模块。
"""

import csv
import os
import re
import sys
import tempfile
import time
import unittest

# -I 隔离模式下脚本目录不在 sys.path，显式加入才能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import exporter
import wave_view


def make_step_data(n=1000):
    """合成数据：CH0（bit0）前 n/2 为 1、后 n/2 为 0；CH1（bit1）恒为 1。

    位序按本机克隆板实测：CHn -> bitn。
    """
    half = n // 2
    return bytes([0x01 | 0x02] * half + [0x02] * (n - half))


class TestExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='wave_export_test_')

    def test_csv_changes(self):
        data = make_step_data(1000)
        path = os.path.join(self.tmp, 'changes.csv')
        lines = exporter.export_csv(path, data, 1_000_000, mode='changes')
        with open(path, encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
        # 表头 + 初始(0) + CH0变化(500)。CH1 恒为 1 不产生变化行，故数据行 2 条。
        self.assertEqual(lines, 3)          # 返回的是"写入的行数"含表头
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], 'sample')
        self.assertEqual(rows[0][2], 'CH0')
        self.assertEqual([r[0] for r in rows[1:]], ['0', '500'])
        # 变化点 CH0 从 1 变 0，CH1 恒 1
        self.assertEqual(rows[1][2], '1')
        self.assertEqual(rows[2][2], '0')
        self.assertEqual(rows[1][3], '1')
        self.assertEqual(rows[2][3], '1')

    def test_csv_samples(self):
        path = os.path.join(self.tmp, 'samples.csv')
        lines = exporter.export_csv(path, make_step_data(1000), 1_000_000,
                                    mode='samples')
        self.assertEqual(lines, 1001)
        with open(path, encoding='utf-8', newline='') as f:
            self.assertEqual(sum(1 for _ in f), 1001)

    def test_vcd_structure(self):
        path = os.path.join(self.tmp, 'out.vcd')
        lines = exporter.export_vcd(path, make_step_data(1000), 1_000_000,
                                    timescale='1us')
        text = open(path, encoding='ascii').read()
        self.assertGreater(lines, 15)
        self.assertIn('$timescale', text)
        self.assertIn('$var wire 1', text)
        self.assertIn('$enddefinitions $end', text)
        self.assertIn('$scope module logic $end', text)
        self.assertIn('$dumpvars', text)
        self.assertRegex(text, r'(?m)^#\d+$')
        self.assertRegex(text, r'#\d+\n[01]!')
        self.assertRegex(text, r'\$var wire 1 . CH0 \$end')

    def test_binary(self):
        data = make_step_data(1000)
        path = os.path.join(self.tmp, 'raw.bin')
        n = exporter.export_binary(path, data)
        self.assertEqual(n, len(data))
        self.assertEqual(open(path, 'rb').read(), data)


class TestDecimation(unittest.TestCase):
    def setUp(self):
        self.n = 1_000_000
        # CH0 方波（CHn->bitn，故落在 bit0）：前 50 万样本为 1，后 50 万为 0
        self.data = bytes([0x01] * (self.n // 2) + [0x00] * (self.n // 2))
        self.width = 1200

    def test_shape_and_values(self):
        cols = wave_view.decimate_for_display(
            self.data, 1_000_000, 0, 0, self.n, self.width)
        self.assertEqual(cols.shape, (self.width, 2))
        raw = np.frombuffer(self.data, dtype=np.uint8)
        # 手工核对几十列
        for x in list(range(0, 20)) + [100, 200, 300, 500, 599, 600,
                                        601, 700, 900, 1100, 1199]:
            s = x * self.n // self.width
            e = (x + 1) * self.n // self.width
            seg = raw[s:e] & 1
            expect = (int(seg.max()), int(1 - seg.min()))
            self.assertEqual(tuple(cols[x]), expect, f'列 {x} 不符')

    def test_boundary(self):
        cols = wave_view.decimate_for_display(
            self.data, 1_000_000, 0, 0, self.n, self.width)
        last_hi = int(np.where(cols[:, 0] == 1)[0][-1])
        first_lo = int(np.where(cols[:, 1] == 1)[0][0])
        # 理想分界在第 600 列，误差 ≤ 1 像素
        self.assertLessEqual(abs(last_hi + 1 - 600), 1)
        self.assertLessEqual(abs(first_lo - 600), 1)

    def test_channel_bit_alignment(self):
        """三处位提取路径必须给出完全相同的 CH0 数据。

        历史教训：decoder_base、wave_view、exporter 曾各自用 (8-ch) 的旧映射，
        改一处漏一处会让真实数据被错误解读。这条测试锁死一致性。
        """
        import sys as _s
        _s.path.insert(0, '.')
        from decoder_base import SampleStream

        d = bytes([0x01, 0x00, 0x01, 0x01, 0x00] * 200)
        raw = np.frombuffer(d, dtype=np.uint8)
        via_base = SampleStream(d, 1000).channel_bits(0)
        via_view = wave_view.extract_bits(d, 0)
        manual = (raw & 1).astype(np.uint8)
        self.assertTrue(np.array_equal(via_base, via_view), 'decoder_base 与 wave_view 不一致')
        self.assertTrue(np.array_equal(via_view, manual), 'wave_view 与手工位移不一致')

    def test_performance(self):
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            wave_view.decimate_for_display(
                self.data, 1_000_000, 0, 0, self.n, self.width)
            times.append(time.perf_counter() - t0)
        elapsed = sorted(times)[1]  # 中位数
        print(f'\n[性能] 100 万样本 / 1200 列降采样耗时中位数: {elapsed:.6f} s')
        self.assertLess(elapsed, 0.2)


def main():
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestExport))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestDecimation))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    count = result.testsRun
    if result.wasSuccessful():
        print(f'ALL TESTS PASSED ({count} 个用例)')
    else:
        print(f'TESTS FAILED: {len(result.failures)} 失败, '
              f'{len(result.errors)} 错误, 共 {count} 个用例')
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
