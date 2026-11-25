"""环境自检：逐项检查并以 [OK]/[!!]/[XX] 中文报告。"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# -I 模式下脚本目录不在 sys.path，显式加入以便 import logic_core。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic_core as core  # noqa: E402


def line(tag, text):
    print(f"[{tag}] {text}")


def main():
    ok = True

    v = sys.version_info
    line("OK" if v >= (3, 8) else "XX",
         f"Python 版本 {v.major}.{v.minor}.{v.micro}")

    try:
        import numpy
        line("OK", f"numpy 可用（版本 {numpy.__version__}）")
    except Exception as exc:
        ok = False
        line("XX", f"numpy 不可用：{exc}")

    try:
        import tkinter
        line("OK", "tkinter 可用（可以运行图形界面）")
    except Exception as exc:
        ok = False
        line("XX", f"tkinter 不可用：{exc}")

    if core.find_device() is None:
        ok = False
        line("XX", "未检测到设备（VID 0925 PID 3881），请检查 USB 连接")
    else:
        line("OK", "检测到设备 VID 0925 PID 3881")
        try:
            cap, _ = core.backend()
            dev = cap.open_dev()
            try:
                eps = [hex(p) for p, _, _, _ in dev.list_pipes()]
                line("OK" if "0x82" in eps else "!!",
                     f"当前端点：{' '.join(eps)}")
                if "0x82" not in eps:
                    ok = False
                    line("!!", "请先启动一次 Logic.exe，识别到设备后关闭，然后重试")
            finally:
                dev.close()
        except Exception as exc:
            ok = False
            line("XX", f"读取端点失败（设备忙或掉线）：{exc}")

    if ok:
        print("\n结论：全部检查通过，可以开始采集。")
    else:
        print("\n结论：存在未通过项，请按上面的提示处理后重试。")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
