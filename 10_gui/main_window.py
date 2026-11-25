# -*- coding: utf-8 -*-
"""主界面：顶部工具栏 + 波形区 + 状态栏 + 协议解码标签页。"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, '08_fx2'), os.path.join(_ROOT, '03_host'),
           os.path.join(_ROOT, '09_app')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                    # noqa: E402

import wave_view                                      # noqa: E402
from capture_backend import CaptureEngine, format_rate  # noqa: E402
from decoder_panel import DecoderPanel, format_event    # noqa: E402
from exporter import export_csv, export_vcd           # noqa: E402

WAVE_X0 = 60                    # 左侧通道标签固定宽度
LABEL_W = 60
CH_COLORS = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8',
             '#f58231', '#911eb4', '#46f0f0', '#f032e6']


def gui_to_view(ch: int) -> int:
    """界面 CH0..CH7 -> wave_view 通道号。

    wave_view.extract_bits(ch) 现也采用 CHn=bitn（ch8 兼容 bit7），
    与界面通道编号一致，直接透传即可。
    """
    return int(ch)


def gui_to_stream(ch: int) -> int:
    """界面 CH0..CH7 -> SampleStream 通道（CHn=bitn，ch8 兼容 bit7）。"""
    return int(ch)


def channel_summary(data: bytes, rate: int, ch: int) -> str:
    """通道摘要：恒高/恒低/频率。直接读 bitn，不依赖 wave_view 位序。"""
    if not data:
        return '无数据'
    raw = np.frombuffer(data, dtype=np.uint8)
    bits = (raw >> ch) & 1
    ones = int(bits.sum())
    n = len(bits)
    if ones == n:
        return '恒高'
    if ones == 0:
        return '恒低'
    # 用跳变次数估算频率
    changes = int(np.count_nonzero(bits[1:] != bits[:-1]))
    hz = changes * rate / (2 * max(1, n))
    if hz >= 1000:
        return f'{hz / 1000:.2f} kHz'
    return f'{hz:.0f} Hz'


def compute_columns(data: bytes, rate: int, ch: int,
                    view_start: int, view_end: int, width_px: int) -> np.ndarray:
    """绘图用的纯计算封装：调用 wave_view.decimate_for_display 做降采样。

    返回 (width_px, 2) 的 uint8 数组，列 x 的 [has_high, has_low]。
    测试直接断言本函数的返回值，不依赖 Canvas。
    """
    return wave_view.decimate_for_display(data, rate, gui_to_view(ch),
                                          view_start, view_end, width_px)


class MainWindow(tk.Tk):
    """双击即用的采集 / 查看 / 解码主窗口。"""

    def __init__(self):
        super().__init__()
        self.title('逻辑分析仪 · 自研上位机')
        self.minsize(1000, 700)
        self.geometry('1160x760')
        self.engine = CaptureEngine()
        self.data = b''
        self.rate = 4000000
        self.view_start = 0
        self.view_end = 0
        self.cursor_sample = 0
        self._pan_x = None
        self._pan_span = 0
        self._poll_id = None
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._poll()

    def _build_ui(self):
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(side='top', fill='x')
        ttk.Label(bar, text='采样率：').pack(side='left')
        self.rate_var = tk.StringVar(value=format_rate(self.rate))
        rates = self.engine.list_rates()
        self.rate_box = ttk.Combobox(bar, textvariable=self.rate_var, width=10,
                                     values=rates, state='readonly')
        self.rate_box.pack(side='left', padx=2)
        self.rate_box.bind('<<ComboboxSelected>>', self._on_rate)
        ttk.Label(bar, text='时长(秒)：').pack(side='left', padx=(8, 2))
        self.seconds_var = tk.StringVar(value='2')
        self.seconds_entry = ttk.Entry(bar, textvariable=self.seconds_var, width=6)
        self.seconds_entry.pack(side='left')
        self.start_btn = tk.Button(bar, text='开始采集', command=self.start_capture,
                                   bg='#2e9e4f', fg='white', width=10)
        self.start_btn.pack(side='left', padx=6)
        self.stop_btn = ttk.Button(bar, text='停止', command=self.stop_capture,
                                   state='disabled', width=6)
        self.stop_btn.pack(side='left')
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=8)
        ttk.Button(bar, text='打开文件', command=self.open_file).pack(side='left')
        ttk.Button(bar, text='导出 CSV', command=self.export_csv).pack(side='left', padx=4)
        ttk.Button(bar, text='导出 VCD', command=self.export_vcd).pack(side='left')
        ttk.Button(bar, text='适应窗口', command=self.fit_window).pack(side='left', padx=4)
        self.status_var = tk.StringVar(value='未连接')
        ttk.Label(bar, textvariable=self.status_var, foreground='#174a7e').pack(side='right')

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side='top', fill='both', expand=True, padx=6, pady=4)
        wave_tab = ttk.Frame(self.notebook)
        self.notebook.add(wave_tab, text='波形')
        self.canvas = tk.Canvas(wave_tab, bg='white', height=560)
        self.canvas.pack(side='top', fill='both', expand=True)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.canvas.bind('<Button-3>', self.on_right_press)
        self.canvas.bind('<B3-Motion>', self.on_right_drag)
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<Configure>', lambda e: self.refresh())

        self.bottom_var = tk.StringVar(value='总样本 0 | 时长 0 s | 光标 -')
        ttk.Label(self, textvariable=self.bottom_var, anchor='w',
                  relief='sunken').pack(side='bottom', fill='x')
        self.decoder = DecoderPanel(self.notebook, lambda: (self.data, self.rate))
        self.notebook.add(self.decoder, text='协议解码')
        self.decoder.set_enabled(False)

    def _on_rate(self, _event=None):
        self.rate = self.engine.rate_by_name(self.rate_var.get()) or self.rate
        self.refresh_status()

    # ---- 采集控制 ----
    def _poll(self):
        r = self.engine.poll()
        state = r['state']
        if state == 'running':
            self.status_var.set(f"采集中 {int(r['progress'] * 100)}%")
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
        elif state == 'done':
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self._load_data(r['data'], self.rate, announce=False)
            self.status_var.set(f"完成 {len(self.data):,} 样本")
        elif state == 'error':
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.status_var.set('采集失败')
            messagebox.showerror('采集失败', r['error'] or '未知错误')
        self._poll_id = self.after(80, self._poll)

    def start_capture(self):
        try:
            seconds = float(self.seconds_var.get())
        except ValueError:
            messagebox.showwarning('输入错误', '采集时长必须是数字（0.1~30 秒）。')
            return
        if not (0.1 <= seconds <= 30):
            messagebox.showwarning('输入错误', '采集时长需在 0.1~30 秒之间。')
            return
        rate = self.engine.rate_by_name(self.rate_var.get()) or self.rate
        self.rate = rate
        if self.engine.start(rate, seconds):
            self.status_var.set('采集中 0%')

    def stop_capture(self):
        self.engine.stop()
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_var.set('已停止')

    def load_data_from_bytes(self, data: bytes, rate: int):
        """供自测调用：加载原始数据，不弹对话框。"""
        self._load_data(data, rate, announce=False)

    def _load_data(self, data: bytes, rate: int, announce=True):
        self.data = bytes(data or b'')
        self.rate = int(rate)
        self.fit_window()
        self.decoder.set_enabled(bool(self.data))
        if announce:
            self.status_var.set(f'完成 {len(self.data):,} 样本')

    def guess_rate_from_name(self, filename: str) -> int:
        """文件名含 _8m/_4m 等时猜采样率，否则用当前下拉框。"""
        import re
        name = filename.lower()
        m = re.search(r'_(\d+(?:\.\d+)?)\s*m(?:\b|_)', name)
        if m:
            hz = int(float(m.group(1)) * 1_000_000)
            if hz in self.engine.all_rates():
                return hz
        m = re.search(r'_(\d+)\s*k(?:\b|_)', name)
        if m:
            hz = int(m.group(1)) * 1000
            if hz in self.engine.all_rates():
                return hz
        return self.engine.rate_by_name(self.rate_var.get()) or self.rate

    def open_file(self):
        path = filedialog.askopenfilename(
            title='打开采样数据', filetypes=[('二进制采样文件', '*.bin'), ('所有文件', '*.*')])
        if not path:
            return
        try:
            with open(path, 'rb') as f:
                blob = f.read()
        except Exception as e:
            messagebox.showerror('打开失败', f'无法读取文件：{e}')
            return
        guessed = self.guess_rate_from_name(os.path.basename(path))
        self.rate = guessed
        self.rate_var.set(format_rate(guessed))
        self._load_data(blob, guessed, announce=False)
        self.status_var.set(
            f'已加载 {os.path.basename(path)}，采样率按 {format_rate(guessed)} 解读，'
            f'如不对请改下拉框')

    # ---- 波形视图与交互 ----
    def fit_window(self):
        self.view_start = 0
        self.view_end = len(self.data)
        self.refresh()

    def zoom_at(self, frac: float, factor: float):
        total = len(self.data)
        if total == 0:
            return
        span = self.view_end - self.view_start
        new_span = int(max(10, min(total, span * factor)))
        anchor = self.view_start + int(span * frac)
        self.view_start = max(0, min(total - new_span, anchor - int(new_span * frac)))
        self.view_end = self.view_start + new_span
        self.refresh()

    def on_wheel(self, event):
        w = max(1, self.canvas.winfo_width())
        self.zoom_at(event.x / w, 0.8 if event.delta > 0 else 1.25)

    def on_right_press(self, event):
        self._pan_x = event.x
        self._pan_span = self.view_end - self.view_start

    def on_right_drag(self, event):
        if self._pan_x is None or not self.data:
            return
        total = len(self.data)
        w = max(1, self.canvas.winfo_width())
        dx = int((event.x - self._pan_x) / w * self._pan_span)
        self.view_start = max(0, min(max(0, total - self._pan_span),
                                     self.view_start - dx))
        self.view_end = self.view_start + self._pan_span
        self._pan_x = event.x
        self.refresh()

    def on_click(self, event):
        if not self.data:
            return
        w = max(1, self.canvas.winfo_width())
        frac = max(0.0, min(1.0, event.x / w))
        span = self.view_end - self.view_start
        s = self.view_start + int(span * frac)
        self.cursor_sample = max(0, min(len(self.data) - 1, s))
        self.canvas.delete('cursor')
        self.canvas.create_line(event.x, 0, event.x, self.canvas.winfo_height(),
                                fill='black', dash=(3, 3), tags='cursor')
        self.refresh_status()

    def refresh(self):
        if not self.data:
            self.canvas.delete('wave')
            return
        w = max(WAVE_X0 + 1, self.canvas.winfo_width() or 1000)
        self.canvas.delete('wave')
        h = max(8 * 40, self.canvas.winfo_height() or 560)
        band = h // 8
        for ch in range(8):
            y_hi = ch * band + 6
            y_lo = (ch + 1) * band - 6
            color = CH_COLORS[ch]
            self.canvas.create_text(30, (y_hi + y_lo) // 2,
                                    text=f'CH{ch}  {channel_summary(self.data, self.rate, ch)}',
                                    fill=color, tags='wave')
            cols = compute_columns(self.data, self.rate, ch,
                                   self.view_start, self.view_end, w)
            for x in range(WAVE_X0, w):
                hi, lo = cols[x, 0], cols[x, 1]
                if hi and lo:
                    self.canvas.create_line(x, y_hi, x, y_lo, fill=color, tags='wave')
                elif hi:
                    self.canvas.create_line(x, y_hi, x + 1, y_hi, fill=color, tags='wave')
                else:
                    self.canvas.create_line(x, y_lo, x + 1, y_lo, fill=color, tags='wave')
        self.refresh_status()

    def refresh_status(self):
        total = len(self.data)
        dur = total / self.rate if self.rate else 0
        part = f'总样本 {total:,} | 时长 {dur:.6g} s'
        if total:
            s = min(self.cursor_sample, total - 1)
            vals = ' '.join(f'CH{c}={(self.data[s] >> c) & 1}' for c in range(8))
            part += f' | 光标 样本{s} ({s / self.rate:.9g} s) {vals}'
        else:
            part += ' | 光标 -'
        self.bottom_var.set(part)

    # ---- 导出与关闭 ----
    def export_csv(self):
        if not self.data:
            messagebox.showwarning('提示', '没有数据可导出。')
            return
        path = filedialog.asksaveasfilename(title='导出 CSV',
                                             defaultextension='.csv',
                                             filetypes=[('CSV 文件', '*.csv')])
        if not path:
            return
        try:
            export_csv(path, self.data, self.rate, channels=list(range(8)))
            self.status_var.set(f'已导出 {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('导出失败', str(e))

    def export_vcd(self):
        if not self.data:
            messagebox.showwarning('提示', '没有数据可导出。')
            return
        path = filedialog.asksaveasfilename(title='导出 VCD',
                                             defaultextension='.vcd',
                                             filetypes=[('VCD 文件', '*.vcd')])
        if not path:
            return
        try:
            export_vcd(path, self.data, self.rate, channels=list(range(8)))
            self.status_var.set(f'已导出 {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('导出失败', str(e))

    def _on_close(self):
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
        self.engine.close()
        self.destroy()
