"""logic_core 自测（unittest，无需第三方包）。

运行：python -I test_core.py
"""

import os
import sys
import threading
import time
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic_core as core  # noqa: E402


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = core.LogicDevice()
        cls.ready, cls.why = cls.dev.is_ready()
        if not cls.ready:
            raise unittest.SkipTest(f"设备不可用：{cls.why}")

    @classmethod
    def tearDownClass(cls):
        cls.dev.close()

    def test_01_ready(self):
        """设备存在且初始化完成时 is_ready 为 True。"""
        self.assertTrue(self.ready, self.why)

    def test_02_channel_freq(self):
        """CH0 上 50 kHz 方波，测得频率应在 50000±200 Hz。"""
        r = self.dev.capture(1000000, 1.0)
        arr = r.channel(0).astype("uint8")
        # 按跳变间隔估算频率（下降沿计数）。
        edges = (arr[1:] == 0) & (arr[:-1] == 1)
        n_edge = int(edges.sum())
        freq = n_edge * r.rate_hz / r.n_samples
        self.assertTrue(abs(freq - 50000) <= 200,
                        f"实测 {freq:.0f} Hz，期望 50000±200 Hz")

    def test_03_achievement(self):
        """4 MHz / 2 秒采集达成率应高于 0.95。"""
        r = self.dev.capture(4000000, 2.0)
        self.assertGreater(r.achievement(), 0.95,
                           f"达成率仅 {r.achievement():.3f}")

    def test_04_concurrent_guard(self):
        """采集进行中再次 capture 应立即抛中文异常。"""
        dev2 = core.LogicDevice()
        result = {}
        started = threading.Event()

        def slow():
            started.set()
            try:
                result["r"] = dev2.capture(1000000, 1.0)
            except Exception as exc:
                result["err"] = exc

        t = threading.Thread(target=slow, daemon=True)
        t.start()
        started.wait(5)
        time.sleep(0.3)
        try:
            with self.assertRaisesRegex(core.LogicError, "上一次采集尚未结束"):
                dev2.capture(1000000, 0.1)
        finally:
            t.join(timeout=15)
        self.assertIn("r", result, f"后台采集未成功：{result.get('err')}")
        dev2.close()

    def test_05_close_twice(self):
        """close() 重复调用不抛异常。"""
        d = core.LogicDevice()
        d.open()
        d.close()
        d.close()

    def test_06_realtime_capture(self):
        """1 MHz 采 2 秒，样本数在 1,900,000 ~ 2,100,000。"""
        r = self.dev.capture(1000000, 2.0)
        self.assertTrue(1900000 <= r.n_samples <= 2100000,
                        f"样本数 {r.n_samples} 超出范围")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CoreTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"用例数：{result.testsRun}")
    if result.wasSuccessful():
        print("ALL TESTS PASSED")
    sys.exit(0 if result.wasSuccessful() else 1)
