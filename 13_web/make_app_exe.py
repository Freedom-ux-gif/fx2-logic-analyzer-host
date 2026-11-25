# -*- coding: utf-8 -*-
"""把 13_web 网页上位机打包成单文件 exe（LogicWeb.exe）。"""
from __future__ import annotations

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_THIS_DIR)
_BUILD = os.path.join(_THIS_DIR, "build")
_DIST = os.path.join(_THIS_DIR, "dist_app")


def fail(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    raise SystemExit(1)


def check_prereqs() -> object:
    index = os.path.join(_THIS_DIR, "static", "index.html")
    if not os.path.isfile(index):
        fail(f"缺少静态首页：{index}")
    for name in ("08_fx2", "09_app", "12_trigger", "03_host"):
        d = os.path.join(_PARENT, name)
        if not os.path.isdir(d):
            fail(f"缺少依赖目录：{d}")
    try:
        import PyInstaller
    except ImportError:
        fail("未安装 PyInstaller，无法打包。请先安装后重试。")
    print(f"前置检查通过：{index}")
    print(f"PyInstaller 版本：{PyInstaller.__version__}")
    return PyInstaller


def build_cmd() -> list[str]:
    # Windows 下 --add-data 用分号分隔源和目标；整条命令以 list 传给
    # subprocess，避免路径带空格时被 shell 拆开。
    add_data = [
        (os.path.join(_THIS_DIR, "static"), "static"),
        (os.path.join(_PARENT, "08_fx2"), "08_fx2"),
        (os.path.join(_PARENT, "09_app"), "09_app"),
        (os.path.join(_PARENT, "12_trigger"), "12_trigger"),
        (os.path.join(_PARENT, "03_host"), "03_host"),
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "LogicWeb",
        "--distpath", _DIST,
        "--workpath", _BUILD,
        # spec 文件也放进 build/，不在项目根目录留下额外文件。
        "--specpath", _BUILD,
        "--noconfirm",
    ]
    for src, dst in add_data:
        cmd += ["--add-data", f"{src}{os.pathsep}{dst}"]
    for mod in ("ctypes", "ctypes.wintypes", "http.server",
                "socketserver", "email.utils"):
        cmd += ["--hidden-import", mod]
    cmd.append(os.path.join(_THIS_DIR, "launcher.py"))
    return cmd


def main() -> int:
    check_prereqs()
    cmd = build_cmd()
    print("开始打包，命令：")
    print("  " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=_THIS_DIR)
    if proc.returncode != 0:
        fail(f"PyInstaller 打包失败，退出码 {proc.returncode}")

    exe = os.path.join(_DIST, "LogicWeb.exe")
    if not os.path.isfile(exe):
        fail(f"打包结束但未找到产物：{exe}")
    size = os.path.getsize(exe)
    print(f"打包完成：{exe}")
    print(f"exe 大小：{size / 1024 / 1024:.1f} MB（{size} 字节）")

    print("冒烟测试：LogicWeb.exe --check")
    # --noconsole 的 exe 默认 stdout 全缓冲，父进程用管道捕获时会因
    # 缓冲区未 flush 而一直等待；设置 PYTHONUNBUFFERED 让输出即时写出。
    smoke_env = os.environ.copy()
    smoke_env["PYTHONUNBUFFERED"] = "1"
    try:
        smoke = subprocess.run([exe, "--check"], timeout=90, env=smoke_env)
    except subprocess.TimeoutExpired:
        fail("冒烟测试超时（90 秒）")
    if smoke.returncode != 0:
        fail(f"冒烟测试失败，退出码 {smoke.returncode}")
    print("冒烟测试通过（退出码 0）")
    print("=" * 56)
    print("打包成功！")
    print(f"  exe 路径：{exe}")
    print(f"  exe 大小：{size / 1024 / 1024:.1f} MB")
    print("  用法：双击 LogicWeb.exe，浏览器会自动打开上位机界面。")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
