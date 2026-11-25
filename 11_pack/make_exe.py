"""用 PyInstaller 把 guitest_app.py 打成单文件 exe，并自动冒烟测试。

运行：python -I make_exe.py
产物：dist/LogicScope.exe
"""
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = "LogicScope"
ENTRY = os.path.join(HERE, "guitest_app.py")
EXE = os.path.join(HERE, "dist", NAME + ".exe")


def sep():
    return ";" if sys.platform == "win32" else ":"


def main():
    import PyInstaller

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", NAME,
        "--distpath", os.path.join(HERE, "dist"),
        "--workpath", os.path.join(HERE, "build"),
        "--specpath", HERE,
        "--clean",
        "--noconfirm",
        # winusb.py 用 `from ctypes import wintypes`，冻结环境需显式收集。
        "--hidden-import", "ctypes",
        "--hidden-import", "ctypes.wintypes",
        # 后端模块位于上级目录，显式作为数据文件带入 exe。
        "--add-data", os.path.join(ROOT, "08_fx2") + sep() + "08_fx2",
        "--add-data", os.path.join(ROOT, "03_host") + sep() + "03_host",
        ENTRY,
    ]
    print("执行打包命令：")
    print("  " + " ".join(cmd))
    print(f"PyInstaller 版本：{PyInstaller.__version__}")
    rc = subprocess.run(cmd, cwd=HERE).returncode
    if rc != 0:
        print(f"[XX] PyInstaller 打包失败，退出码 {rc}")
        return rc
    if not os.path.isfile(EXE):
        print(f"[XX] 未找到产物 {EXE}")
        return 3
    size = os.path.getsize(EXE)
    print(f"[OK] 打包成功：{EXE}（{size:,} 字节）")

    print("开始冒烟测试：exe --version")
    try:
        smoke = subprocess.run([EXE, "--version"], timeout=30,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print("[XX] 冒烟测试超时（30 秒）")
        return 4
    print(f"  退出码：{smoke.returncode}")
    print(f"  输出：{smoke.stdout.strip()}")
    if smoke.stderr.strip():
        print(f"  错误输出：{smoke.stderr.strip()}")
    if smoke.returncode != 0:
        print("[XX] 冒烟测试失败")
        return smoke.returncode
    print("[OK] 冒烟测试通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
