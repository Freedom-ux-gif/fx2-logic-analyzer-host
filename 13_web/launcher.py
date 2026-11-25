# -*- coding: utf-8 -*-
"""逻辑分析仪启动器：双击 start.bat 或运行 `python -I launcher.py`。"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _resource_dir() -> str:
    """打包后资源在 sys._MEIPASS，源码运行时在当前目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return base


def _add_resource_paths(base: str) -> None:
    """把依赖模块目录加入 sys.path（server.py 在 import 时会用到）。"""
    for sub in ("08_fx2", "09_app", "12_trigger", "03_host"):
        p = os.path.join(base, sub)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


_BASE_DIR = _resource_dir()
# 打包后依赖在 _MEIPASS 下；源码模式下从父目录取（与 server.py 的 _ROOT 一致）。
_add_resource_paths(_BASE_DIR)
_add_resource_paths(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _THIS_DIR)
import server as srv

# server.py 的 STATIC_DIR 由 __file__ 推出，打包后会指向临时解压目录；
# 在起服务前直接改为打包资源目录（模块级变量，运行时读取）。
srv.STATIC_DIR = os.path.join(_BASE_DIR, "static")

PORT_START = 8421
PORT_END = 8430


def find_free_port(start: int = PORT_START, end: int = PORT_END) -> int:
    """从 start 试到 end，返回第一个能绑定的端口。"""
    for port in range(start, end + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError(f"{start} 到 {end} 端口都被占用，无法启动服务")


def probe_device() -> dict:
    dev, occupied = srv.device_status()
    dev["occupied"] = occupied
    return dev


def print_banner(port: int, dev: dict) -> None:
    url = f"http://127.0.0.1:{port}"
    print("=" * 56)
    print("  逻辑分析仪网页上位机 · 本地服务")
    print("=" * 56)
    print(f"  访问地址（可点击）：{url}")
    print(f"  实际端口：{port}")
    print(f"  日志文件：{srv.LOG_PATH}")
    print(f"  采集文件目录：{srv.CAPTURE_DIR}")
    print("-" * 56)
    if dev.get("occupied"):
        print("  [警告] 设备打开失败：可能被其它程序占用。")
        print("         请关闭正在运行的 LogicScope.exe / Logic.exe 后重试。")
    elif not dev.get("present"):
        print("  [警告] 未检测到逻辑分析仪，请检查 USB 线是否插好。")
    elif not dev.get("initialized"):
        print("  [警告] 设备缺少 0x82 端点（未初始化）。")
        print("         请先启动一次 Logic.exe 初始化设备，再刷新页面。")
    else:
        print("  设备状态：已就绪（端点含 0x82）")
    print("-" * 56)
    print("  按 Ctrl+C 停止服务")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="逻辑分析仪网页上位机启动器")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--port", type=int, default=None, help="指定端口（默认自动从 8421 起找空闲）")
    ap.add_argument("--check", action="store_true", help="只做自检后退出（用于验收）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = _resource_dir()
    for sub in ("08_fx2", "09_app", "12_trigger", "03_host"):
        p = os.path.join(base, sub)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    srv.STATIC_DIR = os.path.join(base, "static")
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("正在检查设备状态……")
    dev = probe_device()
    if dev.get("occupied"):
        print("设备打开失败：可能被其它程序占用。")
        print("请关闭正在运行的 LogicScope.exe / Logic.exe 后重试。")
    elif not dev.get("present"):
        print("未检测到设备，请检查 USB 连接。")
    elif not dev.get("initialized"):
        print("设备未初始化（缺 0x82），请先启动一次 Logic.exe。")

    port = args.port if args.port is not None else find_free_port()
    if args.check:
        print(f"自检完成：端口 {port}，设备状态：{dev}")
        srv.log_line(f"自检 端口={port} 设备={dev}")
        return 0

    http_server = srv.create_server(port=port)
    actual_port = http_server.server_address[1]
    print_banner(actual_port, dev)
    srv.log_line(f"启动器启动 127.0.0.1:{actual_port} 设备={dev}")

    if not args.no_browser:
        url = f"http://127.0.0.1:{actual_port}"
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    worker = threading.Thread(target=http_server.serve_forever, daemon=True)
    worker.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务……")
    finally:
        http_server.shutdown()
        http_server.server_close()
        srv.log_line("服务已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
