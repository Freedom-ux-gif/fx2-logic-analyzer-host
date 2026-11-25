# -*- coding: utf-8 -*-
"""GUI 自测：python -I test_gui.py（只用 unittest，无需 pytest）。"""
import os
import sys
import tempfile
import time
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS)
for _p in (_THIS, os.path.join(_ROOT, '09_app'), os.path.join(_ROOT, '08_fx2'),
           os.path.join(_ROOT, '03_host')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

import capture_backend as cb
import decoder_panel as dp
import main_window as mw
import synth


class CaptureEngineStateTest(unittest.TestCase):
    def test_state_machine_idle_running_done_with_mock(self):
        """用 mock 替换 cv.capture_timed，不真的采设备。"""
        orig_capture_timed, orig_open = cb.cv.capture_timed, cb.cv.open_dev
        # 2048 字节 / 0.000512 s = 4 MHz，达成率应为 1.0
        fake = b'\xaa' * 2048

        def fake_capture_timed(dev, delay, seconds, n_readers=3):
            time.sleep(0.02)
            return fake, 2048 / 4_000_000

        try:
            cb.cv.capture_timed = fake_capture_timed
            cb.cv.open_dev = lambda: object()
            e = cb.CaptureEngine()
            self.assertEqual(e.poll()['state'], 'idle')
            e.start(4000000, 0.05)
            self.assertEqual(e.poll()['state'], 'running')
            deadline = time.monotonic() + 3
            while e.poll()['state'] == 'running' and time.monotonic() < deadline:
                time.sleep(0.01)
            r = e.poll()
            self.assertEqual(r['state'], 'done')
            self.assertEqual(r['data'], fake)
            self.assertGreaterEqual(r['progress'], 0.99)
            self.assertAlmostEqual(r['achieved'], 1.0, places=2)
            e.close()
        finally:
            cb.cv.capture_timed = orig_capture_timed
            cb.cv.open_dev = orig_open

    def test_error_path_device_none_chinese(self):
        orig_open = cb.cv.open_dev
        try:
            cb.cv.open_dev = lambda: None
            e = cb.CaptureEngine()
            e.start(4000000, 0.05)
            deadline = time.monotonic() + 3
            while e.poll()['state'] == 'running' and time.monotonic() < deadline:
                time.sleep(0.01)
            r = e.poll()
            self.assertEqual(r['state'], 'error')
            self.assertIsNone(r['data'])
            self.assertTrue(r['error'] and any('\u4e00' <= c <= '\u9fff'
                                               for c in r['error']), r['error'])
            e.close()
        finally:
            cb.cv.open_dev = orig_open


class WaveDecimationTest(unittest.TestCase):
    def test_pixel_columns_and_edge_position(self):
        """1000 样本方波：400 低 + 600 高，分界误差 <=1 像素。"""
        width = 1000
        raw = np.zeros(1000, dtype=np.uint8)
        raw[400:] = 1
        cols = mw.compute_columns(raw.tobytes(), 1000, 0, 0, 1000, width)
        self.assertEqual(cols.shape, (width, 2))
        edges = [x for x in range(1, width)
                 if int(cols[x, 0]) != int(cols[x - 1, 0])]
        self.assertEqual(edges, [400], f'边沿列 {edges}')
        self.assertLessEqual(abs(edges[0] - 400), 1)
        self.assertTrue(bool(cols[0, 1]) and not bool(cols[0, 0]))
        self.assertTrue(bool(cols[-1, 0]) and not bool(cols[-1, 1]))

    def test_all_high_display(self):
        """无信号时全 0xFF：不崩、摘要为恒高。"""
        data = b'\xff' * 1000
        cols = mw.compute_columns(data, 4000000, 3, 0, 1000, 100)
        self.assertEqual(cols.shape, (100, 2))
        for ch in range(8):
            self.assertEqual(mw.channel_summary(data, 4000000, ch), '恒高')


class DecodeIntegrationTest(unittest.TestCase):
    def test_uart_synth_hi(self):
        """synth 造在 CH0 上的 'Hi'，CH0 直接透传给解码器。"""
        data = synth.synth_uart('Hi', 115200, 1000000, channel=0)
        events = dp.run_decode(data, 1000000, 'UART',
                               {'channel': '0', 'baud': '115200',
                                'parity': 'none', 'stop_bits': '1'})
        values = [e.data['value'] for e in events if e.kind == 'byte']
        self.assertEqual(values, [72, 105])
        self.assertEqual([dp.format_event(e, 1000000)
                          for e in events if e.kind == 'byte'],
                         [('字节', "0x48 'H'"), ('字节', "0x69 'i'")])

    def test_channel_bits_ch0_matches_raw_bit0(self):
        """SampleStream.channel_bits(0) 必须与 (data & 1) 逐样本完全相等。"""
        from decoder_base import SampleStream
        raw = bytes((i * 37 + 11) & 0xFF for i in range(1024))
        stream = SampleStream(raw, 1000000)
        via_stream = stream.channel_bits(0)
        direct = np.frombuffer(raw, dtype=np.uint8) & 1
        np.testing.assert_array_equal(via_stream, direct)
        # 真实数据上 CH0 的边沿数也必须用两种算法一致
        edges_stream = int(np.count_nonzero(via_stream[1:] != via_stream[:-1]))
        edges_direct = int(np.count_nonzero(direct[1:] != direct[:-1]))
        self.assertEqual(edges_stream, edges_direct)

    def test_i2c_spi_ch0_direct(self):
        """CH0 作为 SCL/SCK 直接透传，不经任何 remap。"""
        d_i2c = synth.synth_i2c([{'addr': 0x50, 'rw': 0, 'data': [0x01]}],
                                1000000, scl_ch=0, sda_ch=1)
        i2c = dp.run_decode(d_i2c, 1000000, 'I2C', {'scl': '0', 'sda': '1'})
        addr = [e for e in i2c if e.kind == 'address']
        self.assertEqual(len(addr), 1)
        self.assertEqual(addr[0].data['addr'], 0x50)
        d_spi = synth.synth_spi([0xAA], 1000000, sck_ch=0, mosi_ch=1, cs_ch=2)
        spi = dp.run_decode(d_spi, 1000000, 'SPI',
                            {'sck': '0', 'mosi': '1', 'cs': '2',
                             'cpol': '0', 'cpha': '0'})
        words = [e for e in spi if e.kind == 'word']
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0].data['value'], 0xAA)

    def test_decode_bad_params_raises(self):
        with self.assertRaises(ValueError):
            dp.run_decode(b'', 1000000, 'UART',
                          {'channel': '0', 'baud': '9600',
                           'parity': 'none', 'stop_bits': '1'})


class FileReplayTest(unittest.TestCase):
    def test_load_bin(self):
        """写临时 .bin，用 MainWindow._load_data 走真实加载路径。"""
        blob = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'wave_4m_test.bin')
            with open(path, 'wb') as f:
                f.write(blob)
            with open(path, 'rb') as f:
                loaded = f.read()
            # 不创建窗口：只在实例上调用纯数据加载逻辑
            win = mw.MainWindow.__new__(mw.MainWindow)
            win.data = b''
            win.rate = 4000000
            win.cursor_sample = 0
            win.view_start = 0
            win.view_end = 0
            win.canvas = None
            win.decoder = type('D', (), {'set_enabled': lambda self, v: None})()
            win.bottom_var = type('V', (), {'set': lambda self, v: None})()
            win.status_var = type('V', (), {'set': lambda self, v: None})()
            win.fit_window = mw.MainWindow.fit_window.__get__(win)
            win.refresh = lambda: None
            win.refresh_status = lambda: None
            win._load_data(loaded, 4000000, announce=False)
        self.assertEqual(len(win.data), len(blob))
        self.assertEqual(win.data, blob)
        self.assertEqual(win.view_end, len(blob))


class RealDeviceVolumeTest(unittest.TestCase):
    """真机 4MHz/1s 数据量回归：防止退回单读线程（只拿到约 5%）。"""

    @unittest.skipUnless(os.environ.get('GUI_REAL_DEVICE') == '1',
                         '设置 GUI_REAL_DEVICE=1 后运行真机采集测试')
    def test_4mhz_1s_volume_over_3_8m(self):
        e = cb.CaptureEngine()
        try:
            e.start(4000000, 1.0)
            deadline = time.monotonic() + 10
            while e.poll()['state'] == 'running' and time.monotonic() < deadline:
                time.sleep(0.05)
            r = e.poll()
            self.assertEqual(r['state'], 'done', r['error'])
            n = len(r['data'] or b'')
            self.assertGreater(n, 3_800_000,
                               f'4MHz/1s 只采到 {n} 字节，疑似退回单读线程')
            self.assertLess(n, 4_200_000)
        finally:
            e.close()


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    print(f'ALL TESTS PASSED ({result.testsRun} cases)' if result.wasSuccessful()
          else 'TESTS FAILED')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
