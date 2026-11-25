# -*- coding: utf-8 -*-
"""入口：python run_gui.py [--headless-check]"""
import os
import sys
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, '08_fx2'), os.path.join(_ROOT, '03_host'),
           os.path.join(_ROOT, '09_app')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)


def headless_check() -> int:
    """无 GUI 环境的导入与逻辑自检。"""
    import numpy as np
    from capture_backend import CaptureEngine, format_rate
    from decoder_panel import format_event, run_decode
    import main_window as mw
    import decoder_i2c, decoder_spi, decoder_uart, exporter, synth, wave_view

    e = CaptureEngine()
    assert len(e.list_rates()) == 10, '采样率档位不是 10'
    assert e.rate_by_name('8 MHz') == 8000000
    assert format_rate(4000000) == '4 MHz'

    # 降采样：1000 样本，前 400 低后 600 高，CH0
    raw = np.zeros(1000, dtype=np.uint8)
    raw[400:] = 1
    cols = mw.compute_columns(raw.tobytes(), 1000, 0, 0, 1000, 1000)
    assert cols.shape == (1000, 2)
    edges = [x for x in range(1, 1000) if int(cols[x, 0]) != int(cols[x - 1, 0])]
    assert edges == [400], f'降采样边沿错位：{edges}'

    # 解码：synth 造 'Hi'
    d = synth.synth_uart('Hi', 115200, 1000000, channel=1)
    ev = run_decode(d, 1000000, 'UART',
                    {'channel': '1', 'baud': '115200',
                     'parity': 'none', 'stop_bits': '1'})
    vals = [x.data['value'] for x in ev if x.kind == 'byte']
    assert vals == [72, 105], f'UART 解码错误：{vals}'
    assert format_event([x for x in ev if x.kind == 'byte'][0], 1000000)[1] == "0x48 'H'"
    print('HEADLESS OK')
    return 0


def main() -> int:
    if '--headless-check' in sys.argv:
        return headless_check()
    try:
        import tkinter as tk
        from main_window import MainWindow
        app = MainWindow()
        app.mainloop()
        return 0
    except Exception:
        msg = traceback.format_exc()
        print(msg, file=sys.stderr)
        try:
            import tkinter.messagebox as mb
            mb.showerror('程序错误', msg)
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
