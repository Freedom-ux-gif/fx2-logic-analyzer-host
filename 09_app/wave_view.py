# -*- coding: utf-8 -*-
"""逻辑分析仪波形查看器（tkinter 实现）。

核心是 draw_waveform 调用的纯计算函数 decimate_for_display：
把海量样本按像素列做降采样，用 numpy 的 reduceat 一次算出每列的
「是否有高电平 / 是否有低电平」，避免逐样本 Python 循环，
使 24MHz 级别数据也能流畅重绘。

无 GUI 环境下本模块同样可导入（tk 为 None），便于 headless 自测降采样逻辑。
"""

import time  # noqa: F401  保留供性能测量参考

# 防御性导入：无图形环境时能 import 本模块做纯计算测试
try:
    import tkinter as tk
except Exception as _tk_err:  # pragma: no cover - 仅 headless 触发
    tk = None
    print(f'提示：tkinter 不可用，波形界面功能关闭（{_tk_err}）。纯计算函数仍可用。')

import numpy as np

# 10 档采样率（Hz）
RATES = [24_000_000, 16_000_000, 12_000_000, 8_000_000, 4_000_000,
         2_000_000, 1_000_000, 500_000, 250_000, 200_000]

# 8 个通道固定颜色（区分度高）
CHANNEL_COLORS = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8',
                  '#f58231', '#911eb4', '#46f0f0', '#f032e6']

# 防御性导入另一个执行手可能提供的流类型；本模块功能不依赖它
try:
    from decoder_base import SampleStream  # noqa: F401
    _HAS_BASE = True
except Exception:
    SampleStream = None
    _HAS_BASE = False


def extract_bits(data: bytes, channel: int) -> np.ndarray:
    """解出单个通道的 0/1 向量，numpy 向量化。

    通道编号 0..7，直接对应 bit 位：CH0=bit0 … CH7=bit7。
    这是本机克隆板的实测映射（与 sigrok 文档的 CH1=bit7 相反）。
    允许传 8，按 bit7 处理，仅为不破坏旧调用。
    """
    if not 0 <= channel <= 8:
        raise ValueError(f'通道号 {channel} 超出范围 0..7（允许 8 兼容）')
    bit = 7 if channel == 8 else channel
    raw = np.frombuffer(data, dtype=np.uint8)
    return ((raw >> bit) & 1).astype(np.uint8)


def decimate_for_display(data: bytes, rate: int, channel: int,
                         view_start: int, view_end: int,
                         width_px: int) -> np.ndarray:
    """像素级降采样（纯计算，不依赖 GUI）。

    每个像素列对应 (view_end-view_start)/width_px 个样本：
    对该范围内的样本同时算 max 与 min，得到 [has_high, has_low]。
    返回形状 (width_px, 2) 的 uint8 数组。
    当可视样本数少于像素列数时，每列取其起点对应的单个样本。
    """
    if width_px <= 0:
        raise ValueError('width_px 必须为正整数')
    total = len(data)
    start = max(0, min(int(view_start), total))
    end = max(start, min(int(view_end), total))
    span = end - start
    if span == 0:
        return np.zeros((width_px, 2), dtype=np.uint8)

    bits = extract_bits(data, channel)[start:end]

    if span >= width_px:
        edges = (np.linspace(0, span, width_px + 1, dtype=np.float64)).astype(np.int64)
        # 保证边界严格递增且末端为 span，避免 reduceat 空段
        edges[-1] = span
        for i in range(1, width_px + 1):
            if edges[i] <= edges[i - 1]:
                edges[i] = edges[i - 1] + 1
        edges[-1] = span
        has_high = np.maximum.reduceat(bits, edges[:-1])
        # min 为 0 表示这一列里存在低电平，故取反
        has_low = 1 - np.minimum.reduceat(bits, edges[:-1])
    else:
        # 样本不足一个像素：每列取起点样本（四舍五入到最近样本）
        idx = np.minimum((np.arange(width_px, dtype=np.float64) * span / width_px).astype(np.int64), span - 1)
        vals = bits[idx]
        has_high = vals
        has_low = 1 - vals

    out = np.empty((width_px, 2), dtype=np.uint8)
    out[:, 0] = has_high
    out[:, 1] = has_low
    return out


def draw_waveform(canvas, data: bytes, rate: int, channels: list[int],
                  view_start: int, view_end: int, width_px: int):
    """在 Canvas 上绘制 8 条通道波形；降采样逻辑委托给 decimate_for_display。

    画布按通道数均分为水平带，每通道一条带。
    每个像素列：高低都有则画竖线（表示跳变），仅高/仅低画对应水平段。
    """
    if tk is None or canvas is None:
        return None
    n_ch = len(channels)
    if n_ch == 0:
        return None
    height = int(canvas.cget('height'))
    band_h = height // n_ch
    canvas.delete('wave')
    for row, ch in enumerate(channels):
        y_hi = row * band_h + 6
        y_lo = (row + 1) * band_h - 6
        color = CHANNEL_COLORS[(ch - 1) % len(CHANNEL_COLORS)]
        # 通道标签固定在每条水平带左侧
        canvas.create_text(30, (y_hi + y_lo) // 2, text=f'CH{ch}',
                           fill=color, tags='wave')
        cols = decimate_for_display(data, rate, ch, view_start, view_end, width_px)
        for x in range(60, width_px):
            hi, lo = cols[x, 0], cols[x, 1]
            if hi and lo:
                canvas.create_line(x, y_hi, x, y_lo, fill=color, tags='wave')
            elif hi:
                canvas.create_line(x, y_hi, x + 1, y_hi, fill=color, tags='wave')
            else:
                canvas.create_line(x, y_lo, x + 1, y_lo, fill=color, tags='wave')
    return width_px * n_ch  # 返回绘制的线段数量级参考


def _make_demo_square(freq, rate, seconds, channel, duty=0.5):
    """生成合成方波字节流（仅用于 __main__ 演示，不依赖 synth.py）。"""
    n = int(rate * seconds)
    period = max(1, rate // freq)
    high = max(1, int(period * duty))
    idx = np.arange(n, dtype=np.int64) % period
    bit = (idx < high).astype(np.uint8)
    return bytes((bit << (8 - channel)).astype(np.uint8).tolist())


class WaveViewer(tk.Tk if tk is not None else object):
    """波形查看器主窗口。headless 下 tk 为 None，类退化为 object 不可实例化。"""

    def __init__(self):
        if tk is None:
            raise RuntimeError('当前环境无 tkinter，无法创建波形查看器窗口')
        super().__init__()
        self.title('逻辑分析仪波形查看器')
        self.geometry('1200x700')
        self.data = b''
        self.rate = RATES[7]  # 默认 500k
        self.view_start = 0
        self.view_end = 0
        self.cursor_sample = 0
        self.visible = list(range(1, 9))
        self._build_ui()

    def _build_ui(self):
        """构建工具栏、画布与状态栏。"""
        bar = tk.Frame(self)
        bar.pack(side='top', fill='x')
        tk.Button(bar, text='打开文件', command=self.open_file).pack(side='left')
        self.rate_var = tk.StringVar(value=str(self.rate))
        tk.OptionMenu(bar, self.rate_var, *[str(r) for r in RATES],
                      command=self._on_rate).pack(side='left')
        self.ch_vars = []
        for ch in range(1, 9):
            v = tk.IntVar(value=1)
            self.ch_vars.append(v)
            tk.Checkbutton(bar, text=f'CH{ch}', variable=v,
                           command=self.refresh).pack(side='left')
        tk.Button(bar, text='放大', command=lambda: self.zoom(0.5)).pack(side='left')
        tk.Button(bar, text='缩小', command=lambda: self.zoom(2.0)).pack(side='left')
        tk.Button(bar, text='适应窗口', command=self.fit_window).pack(side='left')
        tk.Entry(bar, textvariable=tk.StringVar(), width=10).pack(side='left')
        self.jump_var = tk.StringVar()
        jump = tk.Entry(bar, textvariable=self.jump_var, width=12)
        jump.pack(side='left')
        jump.bind('<Return>', lambda e: self.jump_to_sample())

        self.canvas = tk.Canvas(self, bg='white', height=560)
        self.canvas.pack(side='top', fill='both', expand=True)
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<Motion>', self.on_motion)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.canvas.bind('<Shift-MouseWheel>', self.on_shift_wheel)
        self.canvas.bind('<Button-3>', self.on_right_press)
        self.canvas.bind('<B3-Motion>', self.on_right_drag)

        self.status = tk.Label(self, text='', anchor='w')
        self.status.pack(side='bottom', fill='x')

    def _on_rate(self, value):
        self.rate = int(value)
        self.refresh()

    def open_file(self):
        """打开原始二进制采样文件并重置视图。"""
        from tkinter import filedialog
        path = filedialog.askopenfilename()
        if not path:
            return
        with open(path, 'rb') as f:
            self.data = f.read()
        self.fit_window()

    def fit_window(self):
        self.view_start = 0
        self.view_end = len(self.data)
        self.refresh()

    def zoom(self, factor):
        """以视图中心为中心缩放，最少显示 10 个样本，最多显示全部。"""
        total = len(self.data)
        if total == 0:
            return
        span = self.view_end - self.view_start
        new_span = int(max(10, min(total, span * factor)))
        mid = (self.view_start + self.view_end) // 2
        self.view_start = max(0, min(total - new_span, mid - new_span // 2))
        self.view_end = self.view_start + new_span
        self.refresh()

    def on_wheel(self, event):
        """鼠标滚轮以指针位置为中心缩放。"""
        total = len(self.data)
        if total == 0:
            return
        w = max(1, self.canvas.winfo_width())
        frac = event.x / w
        anchor = self.view_start + int((self.view_end - self.view_start) * frac)
        factor = 0.8 if event.delta > 0 else 1.25
        span = self.view_end - self.view_start
        new_span = int(max(10, min(total, span * factor)))
        self.view_start = max(0, min(total - new_span, anchor - int(new_span * frac)))
        self.view_end = self.view_start + new_span
        self.refresh()

    def on_shift_wheel(self, event):
        """Shift + 滚轮水平平移。"""
        span = self.view_end - self.view_start
        step = max(1, span // 10) * (1 if event.delta > 0 else -1)
        self.view_start = max(0, min(len(self.data) - span, self.view_start + step))
        self.view_end = self.view_start + span
        self.refresh()

    def on_right_press(self, event):
        self._pan_x = event.x
        self._pan_span = self.view_end - self.view_start

    def on_right_drag(self, event):
        """右键拖动平移。"""
        if not hasattr(self, '_pan_x'):
            return
        total = len(self.data)
        w = max(1, self.canvas.winfo_width())
        dx = (event.x - self._pan_x) / w * self._pan_span
        self.view_start = max(0, min(total - self._pan_span, self.view_start - int(dx)))
        self.view_end = self.view_start + self._pan_span
        self._pan_x = event.x
        self.refresh()

    def on_click(self, event):
        self.update_cursor(event.x)

    def on_motion(self, event):
        self.update_cursor(event.x)

    def update_cursor(self, x):
        """根据画布 x 坐标更新光标竖线与状态栏。"""
        total = len(self.data)
        if total == 0:
            return
        w = max(1, self.canvas.winfo_width())
        frac = min(1.0, max(0.0, x / w))
        s = self.view_start + int((self.view_end - self.view_start) * frac)
        self.cursor_sample = min(s, total - 1)
        self.canvas.delete('cursor')
        self.canvas.create_line(x, 0, x, self.canvas.winfo_height(),
                                fill='black', tags='cursor')
        self.refresh_status()

    def jump_to_sample(self):
        """跳转到指定样本号。"""
        try:
            s = int(self.jump_var.get())
        except ValueError:
            return
        total = len(self.data)
        if total == 0:
            return
        span = self.view_end - self.view_start
        self.view_start = max(0, min(total - span, s - span // 2))
        self.view_end = self.view_start + span
        self.refresh()

    def refresh_status(self):
        """刷新底部状态栏：视图范围、光标样本/时间、各通道值、总样本数。"""
        total = len(self.data)
        s = self.cursor_sample
        t = s / self.rate if self.rate else 0
        vals = []
        for ch in range(1, 9):
            v = ((self.data[s] >> (8 - ch)) & 1) if total else 0
            vals.append(f'CH{ch}={v}')
        self.status.config(text=(f'视图 {self.view_start}~{self.view_end} '
                                 f'({self.view_start / self.rate:.6g}~{self.view_end / self.rate:.6g}s) '
                                 f'| 光标 样本{s} 时间{t:.9g}s | {" ".join(vals)} '
                                 f'| 总样本 {total}'))

    def refresh(self):
        """重绘波形并刷新状态栏。"""
        if not self.data:
            return
        self.visible = [ch for ch, var in enumerate(self.ch_vars, 1) if var.get()] \
            if hasattr(self, 'ch_vars') else list(range(1, 9))
        w = max(1, self.canvas.winfo_width())
        draw_waveform(self.canvas, self.data, self.rate, self.visible,
                      self.view_start, self.view_end, w)
        self.refresh_status()


def _main():
    """生成合成方波并打开查看器，方便人工验证。"""
    rate = 1_000_000
    data = _make_demo_square(freq=1000, rate=rate, seconds=0.1, channel=1)
    viewer = WaveViewer()
    viewer.data = data
    viewer.rate = rate
    viewer.fit_window()
    viewer.mainloop()


if __name__ == '__main__':
    _main()
