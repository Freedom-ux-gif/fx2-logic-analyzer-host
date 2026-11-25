# -*- coding: utf-8 -*-
"""协议解码面板：UART / I2C / SPI，后台线程解码后回主线程填表。"""
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, '08_fx2'), os.path.join(_ROOT, '03_host'),
           os.path.join(_ROOT, '09_app')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from decoder_i2c import decode_i2c                    # noqa: E402
from decoder_spi import decode_spi                    # noqa: E402
from decoder_uart import decode_uart                  # noqa: E402

BAUDS = [9600, 19200, 38400, 57600, 115200, 921600]
CHANNELS = list(range(8))
KIND_CN = {'byte': '字节', 'start': '起始位', 'address': '地址', 'data': '数据',
           'ack': '应答', 'nack': '无应答', 'word': '字', 'stop': '停止',
           'repeat_start': '重复起始', 'frame': '帧', 'cs_assert': '片选有效',
           'cs_deassert': '片选释放', 'parity_error': '校验错误',
           'framing_error': '帧错误'}


def format_event(ev, rate: int) -> tuple[str, str]:
    """把 DecodeEvent 格式化为 (中文类型, 内容列文本)。"""
    kind = ev.kind
    d = ev.data or {}
    content = ''
    if kind == 'byte' and 'value' in d:
        v = d['value']
        ch = d.get('char')
        content = f"0x{v:02X} '{ch}'" if ch else f'0x{v:02X}'
    elif kind == 'address':
        content = f"0x{d.get('addr', 0):02X} ({'读' if d.get('rw') else '写'})"
    elif kind == 'data' and 'value' in d:
        content = f"0x{d['value']:02X}"
    elif kind == 'word' and 'value' in d:
        content = f"0x{d['value']:02X}"
    elif 'hex' in d:
        content = d['hex']
    elif 'value' in d:
        content = str(d['value'])
    else:
        content = kind
    return KIND_CN.get(kind, kind), content


def run_decode(data: bytes, rate: int, proto: str, params: dict):
    """同步解码封装（供后台线程调用）；失败时抛出带中文说明的异常。

    界面 CH0..CH7 直接透传给解码器：SampleStream.channel_bits(ch) 就是
    (raw >> ch) & 1，解码器现也支持 0..7，无需任何重映射。
    """
    if not data:
        raise ValueError('没有可解码的数据，请先采集或打开文件。')
    if rate <= 0:
        raise ValueError('采样率无效。')
    p = proto.upper()
    if p == 'UART':
        return decode_uart(data, rate, int(params['channel']), int(params['baud']),
                           parity=params.get('parity', 'none'),
                           stop_bits=int(params.get('stop_bits', 1)))
    if p == 'I2C':
        return decode_i2c(data, rate, int(params['scl']), int(params['sda']))
    if p == 'SPI':
        cs = params.get('cs')
        return decode_spi(data, rate, int(params['sck']), int(params['mosi']),
                          cs_ch=int(cs) if cs not in (None, '') else None,
                          cpol=int(params.get('cpol', 0)),
                          cpha=int(params.get('cpha', 0)))
    raise ValueError(f'不支持的协议：{proto}')


class DecoderPanel(ttk.Frame):
    """协议解码标签页，由 MainWindow 创建并注入取数回调。"""

    def __init__(self, parent, get_data):
        super().__init__(parent)
        self.get_data = get_data               # () -> (data: bytes, rate: int)
        self._thread = None
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=6, pady=6)
        ttk.Label(top, text='协议：').pack(side='left')
        self.proto = tk.StringVar(value='UART')
        proto_box = ttk.Combobox(top, textvariable=self.proto, width=10,
                                 values=['UART', 'I2C', 'SPI'], state='readonly')
        proto_box.pack(side='left', padx=4)
        proto_box.bind('<<ComboboxSelected>>', lambda e: self._switch_params())
        self.params = ttk.Frame(self)
        self.params.pack(fill='x', padx=6)
        self.decode_btn = ttk.Button(top, text='开始解码', command=self.start_decode)
        self.decode_btn.pack(side='left', padx=12)
        ttk.Button(top, text='清空结果', command=self.clear).pack(side='left')

        cols = ('#', '类型', '起始样本', '时间', '内容')
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=16)
        widths = (60, 100, 120, 150, 320)
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor='w')
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.config(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        scroll.pack(side='left', fill='y', pady=6)
        self._switch_params()

    def _row(self, label, widget):
        row = ttk.Frame(self.params)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label, width=12).pack(side='left')
        widget.pack(side='left', padx=4)

    def _channel_box(self, parent, var, default=0):
        var.set(str(default))
        box = ttk.Combobox(parent, textvariable=var, width=6,
                           values=[str(c) for c in CHANNELS], state='readonly')
        return box

    def _switch_params(self):
        for w in list(self.params.winfo_children()):
            w.destroy()
        p = self.proto.get()
        self.v = {}
        if p == 'UART':
            self.v['channel'] = tk.StringVar(value='0')
            self._row('通道(0-7)', self._channel_box(self.params, self.v['channel']))
            self.v['baud'] = tk.StringVar(value='115200')
            self._row('波特率', ttk.Combobox(self.params, textvariable=self.v['baud'],
                      width=12, values=[str(b) for b in BAUDS]))
            self.v['parity'] = tk.StringVar(value='none')
            self._row('校验', ttk.Combobox(self.params, textvariable=self.v['parity'],
                      width=8, values=['none', 'even', 'odd'], state='readonly'))
            self.v['stop_bits'] = tk.StringVar(value='1')
            self._row('停止位', ttk.Combobox(self.params, textvariable=self.v['stop_bits'],
                      width=6, values=['1', '2'], state='readonly'))
        elif p == 'I2C':
            self.v['scl'] = tk.StringVar(value='0')
            self._row('SCL 通道', self._channel_box(self.params, self.v['scl']))
            self.v['sda'] = tk.StringVar(value='1')
            self._row('SDA 通道', self._channel_box(self.params, self.v['sda']))
        else:
            self.v['sck'] = tk.StringVar(value='0')
            self._row('SCK 通道', self._channel_box(self.params, self.v['sck']))
            self.v['mosi'] = tk.StringVar(value='1')
            self._row('MOSI 通道', self._channel_box(self.params, self.v['mosi']))
            self.v['cs'] = tk.StringVar(value='')
            self._row('CS 通道(可空)', ttk.Combobox(self.params, textvariable=self.v['cs'],
                      width=6, values=[''] + [str(c) for c in CHANNELS]))
            self.v['cpol'] = tk.StringVar(value='0')
            self._row('CPOL', ttk.Combobox(self.params, textvariable=self.v['cpol'],
                      width=6, values=['0', '1'], state='readonly'))
            self.v['cpha'] = tk.StringVar(value='0')
            self._row('CPHA', ttk.Combobox(self.params, textvariable=self.v['cpha'],
                      width=6, values=['0', '1'], state='readonly'))

    def set_enabled(self, enabled: bool):
        """无数据时禁用解码按钮。"""
        self.decode_btn.config(state='normal' if enabled else 'disabled')

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def start_decode(self):
        data, rate = self.get_data()
        if not data:
            messagebox.showwarning('提示', '没有可解码的数据，请先采集或打开文件。')
            return
        if self._thread and self._thread.is_alive():
            messagebox.showinfo('提示', '正在解码，请稍候。')
            return
        try:
            params = {k: v.get() for k, v in self.v.items()}
            params['cs'] = int(params['cs']) if params.get('cs') else None
        except Exception as e:
            messagebox.showerror('参数错误', f'参数不合法：{e}')
            return
        self.decode_btn.config(state='disabled')
        self.clear()

        def work():
            try:
                events = run_decode(data, rate, self.proto.get(), params)
                self.after(0, self._fill, events, rate)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror('解码失败', str(e)))
            finally:
                self.after(0, lambda: self.decode_btn.config(state='normal'))

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def _fill(self, events, rate):
        for i, ev in enumerate(events):
            typ, content = format_event(ev, rate)
            t = ev.start_sample / rate if rate else 0
            self.tree.insert('', 'end', values=(i + 1, typ, ev.start_sample,
                                                f'{t:.9g} s', content))
# __NEXT__
