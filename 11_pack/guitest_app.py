"""LogicScope 图形界面（打包链路验证用，极简但完整）。

用法：
    python -I guitest_app.py              # 启动界面
    python -I guitest_app.py --version    # 打印版本号后退出
    python -I guitest_app.py --selftest   # 真实采集 1 秒 @1MHz 后退出
"""
import os
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# -I / PyInstaller 下显式加入本地模块路径。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import tkinter as tk
from tkinter import ttk

import logic_core as core

VERSION = "LogicScope 1.0"


def do_selftest():
    """真实采集一次并打印结果，成功返回 0。"""
    dev = core.LogicDevice()
    ready, why = dev.is_ready()
    if not ready:
        print(f"[XX] 设备不可用：{why}")
        return 2
    result = dev.capture(1000000, 1.0)
    dev.close()
    print(f"[OK] {result.summary()}")
    print(f"[OK] 样本数 {result.n_samples:,}，原始数据：{result.raw_path}")
    return 0


def draw_wave(canvas, result):
    """把 8 个通道画成方波；按画布宽度做简单像素降采样。"""
    canvas.delete("all")
    w = int(canvas.winfo_width() or 800)
    h = int(canvas.winfo_height() or 400)
    row_h = h / 8
    n = result.n_samples
    # 每像素取一段，段内出现 1 就画高电平（近似波形，足够肉眼观察）。
    for ch in range(8):
        bits = result.channel(ch)
        step = max(1, n // max(w, 1))
        y0 = ch * row_h
        pts = []
        for px in range(min(w, n)):
            seg = bits[px * step:(px + 1) * step]
            high = bool(seg.any())
            pts.extend([(px, y0 + (3 if high else row_h - 3)),
                        (px + 1, y0 + (3 if high else row_h - 3))])
        if pts:
            canvas.create_line(pts, fill="#0060c0", width=1)
        canvas.create_text(4, y0 + row_h / 2, text=f"CH{ch}", anchor="w",
                           fill="#444444")


class App:
    def __init__(self, root):
        self.root = root
        self.dev = core.LogicDevice()
        root.title(VERSION)
        root.geometry("900x520")

        top = ttk.Frame(root, padding=6)
        top.pack(side="top", fill="x")
        self.rate_var = tk.StringVar()
        self.rates = self.dev.rates()
        self.rate_var.set(self.rates[0]["name"])
        ttk.Label(top, text="采样率：").pack(side="left")
        self.combo = ttk.Combobox(top, textvariable=self.rate_var,
                                  values=[r["name"] for r in self.rates],
                                  state="readonly", width=12)
        self.combo.pack(side="left")
        ttk.Label(top, text="时长(秒)：").pack(side="left")
        self.sec_var = tk.StringVar(value="2")
        ttk.Entry(top, textvariable=self.sec_var, width=8).pack(side="left")
        self.btn = ttk.Button(top, text="开始采集", command=self.start)
        self.btn.pack(side="left", padx=8)

        ready, why = self.dev.is_ready()
        self.status = tk.StringVar(value=("设备就绪：" if ready else "提示：") + why)
        self.canvas = tk.Canvas(root, bg="white", height=380)
        self.canvas.pack(side="top", fill="both", expand=True, padx=6)
        ttk.Label(root, textvariable=self.status, anchor="w",
                  padding=6).pack(side="bottom", fill="x")

    def start(self):
        """后台线程采集，不阻塞界面。"""
        if self.btn["state"] != "normal":
            return
        name = self.rate_var.get()
        rate = next((r["hz"] for r in self.rates if r["name"] == name), 1000000)
        try:
            seconds = float(self.sec_var.get())
            if seconds <= 0:
                raise ValueError
        except ValueError:
            self.status.set("错误：时长必须是正数")
            return
        self.btn.config(state="disabled")
        self.status.set("采集中，请稍候……")

        def work():
            try:
                result = self.dev.capture(rate, seconds)
                text = result.summary()
                self.root.after(0, lambda: draw_wave(self.canvas, result))
            except core.LogicError as exc:
                text = f"采集失败：{exc}"
            self.root.after(0, lambda: (self.status.set(text),
                                        self.btn.config(state="normal")))

        threading.Thread(target=work, daemon=True).start()

    def run(self):
        self.root.mainloop()
        self.dev.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--version" in argv:
        print(VERSION)
        return 0
    if "--selftest" in argv:
        return do_selftest()
    root = tk.Tk()
    App(root).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
