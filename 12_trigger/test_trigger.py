# -*- coding: utf-8 -*-
"""test_trigger.py —— 软件触发引擎自测（合成数据 + 真实设备）。"""
from __future__ import annotations

import os
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, '08_fx2'))
sys.path.insert(0, os.path.join(ROOT, '09_app'))

from trigger import (EdgeTrigger, LevelTrigger, PulseWidthTrigger,
                     PatternTrigger, UartStartTrigger)
from triggered_capture import TriggeredCapture, TriggerResult
from synth import synth_uart


class TestSynthetic(unittest.TestCase):
    """全部用合成数据验证触发点计算，不依赖硬件。"""

    def test_edge_rising_at_5000(self):
        d = np.zeros(10000, dtype=np.uint8)
        d[5000:] = 1
        self.assertEqual(EdgeTrigger(0, rising=True).find(d, 4000000), 5000)

    def test_edge_count3(self):
        d = np.zeros(20000, dtype=np.uint8)
        for s, e in ((100, 200), (700, 800), (5000, 5100), (9000, 9100)):
            d[s:e] = 1
        self.assertEqual(EdgeTrigger(0, rising=True, count=3).find(d, 4000000), 5000)

    def test_level_start(self):
        d = np.zeros(10000, dtype=np.uint8)
        d[1234:1500] = 1
        self.assertEqual(LevelTrigger(0, level=1, count=100).find(d, 4000000), 1234)

    def test_pulse_width(self):
        d = np.zeros(10000, dtype=np.uint8)
        d[1000:1100] = 1
        self.assertEqual(PulseWidthTrigger(0, min_samples=50, max_samples=150).find(d, 4000000), 1000)
        self.assertIsNone(PulseWidthTrigger(0, min_samples=200).find(d, 4000000))

    def test_pattern(self):
        d = np.zeros(1000, dtype=np.uint8)
        d[77:99] |= (1 << 0) | (1 << 2)          # CH0=1, CH1=0, CH2=1
        self.assertEqual(PatternTrigger('1x1', [0, 1, 2]).find(d, 4000000), 77)

    def test_uart_start(self):
        baud, rate = 9600, 1000000
        raw = np.frombuffer(synth_uart('AB', baud, rate, channel=0), dtype=np.uint8)
        spb = round(rate / baud)
        idx = UartStartTrigger(0, baud, rate).find(raw, rate)
        self.assertIsNotNone(idx)
        self.assertLessEqual(abs(idx - spb), 1)
        self.assertEqual(raw[idx], 0)           # 起始位为低

    def test_empty_and_invalid(self):
        e = np.array([], dtype=np.uint8)
        for t in (EdgeTrigger(0), LevelTrigger(0), PulseWidthTrigger(0),
                  PatternTrigger('1x', [0, 1]), UartStartTrigger(0, 9600, 1000000)):
            self.assertIsNone(t.find(e, 4000000))
        for make, kw in ((EdgeTrigger, dict(channel=8)), (EdgeTrigger, dict(channel=0, count=0)),
                         (LevelTrigger, dict(channel=-1)), (PatternTrigger, dict(pattern='10', channel_map=[0]))):
            with self.assertRaises(ValueError):
                make(**kw)

class TestRealDevice(unittest.TestCase):
    """真实设备：CH0 上的 50 kHz 方波（仅验证，不修改任何采集后端）。"""

    def test_edge_on_real_wave(self):
        import capture_verified as cv
        dev = cv.open_dev()
        self.assertIsNotNone(dev, '未找到设备，请检查 USB 连接')
        try:
            blob, _ = cv.capture_timed(dev, cv.BY_HZ[4000000][0], 1.0, n_readers=3)
            d = np.frombuffer(blob, dtype=np.uint8)
            self.assertGreater(len(d), 1000, '采集数据过短')
            idx = EdgeTrigger(0, rising=True).find(d, 4000000)
            self.assertIsNotNone(idx, '真实波形上未找到上升沿')
            # idx 可能很小：4 MHz 下 50 kHz 方波的前沿距第 0 个样本
            # 只有十几个样本（20 个半周期），所以只要求 idx >= 1 才能取 idx-1。
            self.assertGreaterEqual(idx, 1)
            self.assertEqual(d[idx - 1] & 1, 0, '触发点前应为低电平')
            self.assertEqual(d[idx] & 1, 1, '触发点应为高电平')
        finally:
            dev.close()

    def test_triggered_capture_e2e(self):
        import capture_verified as cv
        dev = cv.open_dev()
        self.assertIsNotNone(dev)
        try:
            cap = TriggeredCapture(dev, 4000000, EdgeTrigger(0, rising=True), 0.2)
            r = cap.run(1.0)
            self.assertTrue(r.found, r.message)
            ratio = r.trigger_offset / len(r.data)
            self.assertAlmostEqual(ratio, 0.2, delta=0.01)
            self.assertEqual(r.data[r.trigger_offset] & 1, 1)
        finally:
            dev.close()

    def test_performance_10m(self):
        d = np.zeros(10_000_000, dtype=np.uint8)
        d[::1000] = 1
        t0 = time.perf_counter()
        idx = EdgeTrigger(0, rising=True).find(d, 4000000)
        dt = time.perf_counter() - t0
        print(f'\n[性能] 1000 万样本 EdgeTrigger 耗时 {dt:.3f} 秒，结果 {idx}')
        self.assertLess(dt, 1.0)


if __name__ == '__main__':
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestSynthetic))
    suite.addTests(loader.loadTestsFromTestCase(TestRealDevice))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f'ALL TESTS PASSED ({result.testsRun} cases)')
    else:
        sys.exit(1)

