# -*- coding: utf-8 -*-
"""采集封装：把 cv.capture 的读线程与阻塞隔离到后台线程，主线程只 poll。"""
import os
import queue
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, '08_fx2'), os.path.join(_ROOT, '03_host')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import capture_verified as cv
except Exception as _e:                      # 后端缺失时界面仍可启动并给出中文错误
    cv = None
    _IMPORT_ERROR = str(_e)
else:
    _IMPORT_ERROR = None


def format_rate(hz: int) -> str:
    """把 Hz 格式化为界面用的 '8 MHz' / '500 kHz'。"""
    hz = int(hz)
    if hz >= 1_000_000:
        return f'{hz / 1_000_000:g} MHz'
    return f'{hz / 1_000:g} kHz'


class CaptureEngine:
    """采集状态机：idle -> running -> done / error，或用 stop() 回到 idle。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = 'idle'
        self._progress = 0.0
        self._data = None
        self._error = None
        self._achieved = 0.0             # 数据字节数 / (采样率 × 实际数据流时长)
        self._dev = None
        self._thread = None
        self._queue = queue.Queue()          # 预留：线程数据回传通道
        self._stop_flag = threading.Event()
        self._prog_stop = threading.Event()

    def list_rates(self) -> list[str]:
        """返回 10 档中文速率名，顺序与 RATES 一致。"""
        if cv is None:
            return [format_rate(h) for h in (24000000, 16000000, 12000000,
                    8000000, 4000000, 2000000, 1000000, 500000, 250000, 200000)]
        return [format_rate(hz) for hz, _delay, _name in cv.RATES]

    def rate_by_name(self, name: str) -> int:
        """'8 MHz' -> 8000000；找不到返回 0。"""
        table = dict(zip(self.list_rates(), self.all_rates()))
        return int(table.get(str(name).strip(), 0))

    def all_rates(self) -> list[int]:
        if cv is None:
            return [24000000, 16000000, 12000000, 8000000, 4000000,
                    2000000, 1000000, 500000, 250000, 200000]
        return [int(hz) for hz, _d, _n in cv.RATES]

    # ---- 后台线程：绝不触碰 tkinter 对象 ----
    def _open_dev(self):
        if self._dev is not None:
            return self._dev
        if cv is None:
            raise RuntimeError(f'采集后端不可用：{_IMPORT_ERROR}')
        dev = cv.open_dev()                  # 第一次 start 时才打开设备
        if dev is None:
            raise RuntimeError('未找到逻辑分析仪，请检查 USB 是否已插好。')
        pipes = []
        try:
            pipes = [hex(p) for p, _a, _b, _c in dev.list_pipes()]
        except Exception:
            pass
        if pipes and '0x82' not in pipes:
            try:
                dev.close()
            except Exception:
                pass
            raise RuntimeError('设备端点 0x82 缺失，设备未初始化。'
                               '请插上设备后运行一次 Logic.exe 再关闭，然后重试。')
        self._dev = dev
        return dev

    def _worker(self, rate_hz: int, seconds: float):
        self._prog_stop.clear()
        progress_thread = threading.Thread(target=self._progress_loop,
                                           args=(seconds,), daemon=True)
        progress_thread.start()
        try:
            if cv is None:
                raise RuntimeError(f'采集后端不可用：{_IMPORT_ERROR}')
            delay = cv.BY_HZ.get(int(rate_hz), (None, None))[0]
            if delay is None:
                raise RuntimeError(f'不支持的采样率：{rate_hz} Hz')
            dev = self._open_dev()
            # 用 3 读线程的 capture_timed：单线程在 4MHz 只拿到约 5% 数据。
            # 它返回 (data, elapsed)，elapsed 用来算真实达成率。
            blob, elapsed = cv.capture_timed(dev, delay, seconds, n_readers=3)
            if self._stop_flag.is_set():
                self._finish('idle', 0.0, None, None)
                return
            if not blob:
                raise RuntimeError('设备未返回数据（输入端无信号时也会返回全 0xFF，'
                                   '请检查采集是否成功）。')
            achieved = len(blob) / max(float(rate_hz), 1) / max(float(elapsed), 1e-6)
            self._finish('done', 1.0, bytes(blob), None, achieved=achieved)
        except Exception as exc:             # 任何失败都转成中文 error，不向外抛
            self._finish('error', 0.0, None, f'采集失败：{exc}')
        finally:
            self._prog_stop.set()
            progress_thread.join(timeout=1)

    def _progress_loop(self, seconds: float):
        """capture() 无回调，按经过时间线性模拟进度。"""
        t0 = time.monotonic()
        total = max(0.05, float(seconds))
        while not self._prog_stop.is_set() and not self._stop_flag.is_set():
            p = min(0.99, (time.monotonic() - t0) / total)
            with self._lock:
                if self._state == 'running' and p > self._progress:
                    self._progress = p
            self._prog_stop.wait(0.05)

    def _finish(self, state, progress, data, error, achieved=0.0):
        with self._lock:
            self._state = state
            self._progress = progress
            self._data = data
            self._error = error
            self._achieved = float(achieved)
        self._queue.put((state, data, error))

    def start(self, rate_hz: int, seconds: float):
        """启动后台采集线程，立即返回，不阻塞界面。"""
        with self._lock:
            if self._state == 'running':
                return False
            self._state = 'running'
            self._progress = 0.0
            self._data = None
            self._error = None
            self._achieved = 0.0
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._worker,
                                        args=(int(rate_hz), float(seconds)),
                                        daemon=True)
        self._thread.start()
        return True

    def poll(self) -> dict:
        """主循环定时调用，返回状态字典。"""
        with self._lock:
            return {'state': self._state, 'progress': self._progress,
                    'data': self._data, 'error': self._error,
                    'achieved': self._achieved}

    def stop(self):
        """请求停止；cv.capture 无法中断，只把状态复位为 idle。"""
        self._stop_flag.set()
        self._prog_stop.set()
        with self._lock:
            if self._state == 'running':
                self._state = 'idle'
                self._progress = 0.0

    def close(self):
        """关闭设备，释放 USB 句柄。"""
        self.stop()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

# __NEXT__
