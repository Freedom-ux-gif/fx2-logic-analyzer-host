# -*- coding: utf-8 -*-
"""逻辑分析仪本地 HTTP 后端（只监听 127.0.0.1，全部中文错误）。"""
from __future__ import annotations

import functools
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
for _sub in ("03_host", "08_fx2", "09_app", "12_trigger"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

import numpy as np
import capture_verified as cv
import decoder_uart, decoder_i2c, decoder_spi, decoder_can
import trigger as trig
import triggered_capture as tc
import exporter

VERSION = "1.0.0"
STATIC_DIR = os.path.join(_THIS_DIR, "static")
LOG_DIR = os.path.join(_THIS_DIR, "logs")
CAPTURE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "LogicCapture")
LOG_PATH = os.path.join(LOG_DIR, "server_" + datetime.now().strftime("%Y%m%d") + ".log")
MAX_CAPTURES = 20

for _d in (STATIC_DIR, LOG_DIR, CAPTURE_DIR):
    os.makedirs(_d, exist_ok=True)

_log_lock = threading.Lock()


def log_line(text: str) -> None:
    try:
        with _log_lock:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(datetime.now().strftime("%H:%M:%S ") + text + "\n")
    except Exception:
        pass


def occupied_hint(exc: Exception | None = None) -> str:
    """把底层的 ACCESS_DENIED 翻译成用户能看懂的中文提示。"""
    msg = str(exc) if exc else ""
    if "5" in msg or "ACCESS_DENIED" in msg or "权限不足" in msg or "占用" in msg:
        return ("设备打开失败：可能被其它程序占用。请关闭正在运行的 "
                "LogicScope.exe / Logic.exe 后重试。")
    return f"设备打开失败：{msg or '未知原因'}。请确认设备已插好并初始化。"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return str(obj)


class AppState:
    """服务端全局状态：设备锁、采集元数据、事件流。"""

    def __init__(self, inject_delay: float = 0.0):
        self.device_lock = threading.Lock()
        self.captures: OrderedDict[str, dict] = OrderedDict()
        self.meta_lock = threading.Lock()
        self.counter = 0
        self.listeners: list[queue.Queue] = []
        self.listener_lock = threading.Lock()
        self.inject_delay = float(inject_delay)  # 仅用于并发测试注入延迟
        self.signal_present: bool | None = None  # 最近一次采集是否检测到跳变

    def emit(self, kind: str, **kw) -> None:
        payload = dict(type=kind, **kw)
        with self.listener_lock:
            listeners = list(self.listeners)
        for q in listeners:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass

    def add_listener(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self.listener_lock:
            self.listeners.append(q)
        return q

    def remove_listener(self, q: queue.Queue) -> None:
        with self.listener_lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def next_id(self) -> str:
        with self.meta_lock:
            self.counter += 1
            return f"{int(time.time() * 1000)}-{self.counter}"

    def register(self, path: str, rate_hz: int, n_samples: int, elapsed: float,
                 found: bool | None = None, trigger_offset: int | None = None) -> str:
        cid = self.next_id()
        meta = dict(path=path, rate_hz=rate_hz, n_samples=n_samples,
                    elapsed=elapsed, found=found, trigger_offset=trigger_offset)
        with self.meta_lock:
            self.captures[cid] = meta
            while len(self.captures) > MAX_CAPTURES:
                self.captures.popitem(last=False)
        return cid

    def get(self, cid: str) -> dict:
        with self.meta_lock:
            meta = self.captures.get(cid)
            if meta is None:
                raise ApiError(404, f"找不到采集编号 {cid}，可能已超出最近 {MAX_CAPTURES} 次范围")
            return dict(meta)


STATE = AppState()


def check_rate(rate_hz) -> tuple[int, int, str]:
    try:
        hz = int(rate_hz)
    except (TypeError, ValueError):
        raise ApiError(400, f"采样率必须是整数，收到 {rate_hz!r}")
    if hz not in cv.BY_HZ:
        names = "、".join(n for _, _, n in cv.RATES)
        raise ApiError(400, f"不支持的采样率 {hz} Hz。可选：{names}")
    delay, name = cv.BY_HZ[hz]
    return hz, delay, name


def check_seconds(seconds) -> float:
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        raise ApiError(400, f"采集时长必须是数字，收到 {seconds!r}")
    if not 0.05 <= s <= 30.0:
        raise ApiError(400, "采集时长需在 0.05 到 30 秒之间")
    return s


def check_channel(ch, name: str = "通道") -> int:
    try:
        c = int(ch)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name}必须是 0..7 的整数，收到 {ch!r}")
    if not 0 <= c <= 7:
        raise ApiError(400, f"{name}必须是 0..7 的整数，收到 {ch!r}")
    return c


def device_status() -> tuple[dict, bool]:
    """探测设备；返回 (状态字典, 是否被占用)。"""
    result = dict(present=False, initialized=False, endpoints=[], occupied=False)
    try:
        devs = cv.winusb.enumerate_devices()
    except Exception as e:
        result["error"] = occupied_hint(e)
        result["occupied"] = True
        return result, True
    if not devs:
        result["error"] = "未检测到逻辑分析仪，请检查 USB 线是否插好"
        return result, False
    result["present"] = True
    try:
        dev = cv.open_dev()
    except Exception as e:
        result["occupied"] = True
        result["error"] = occupied_hint(e)
        return result, True
    if dev is None:
        result["error"] = "设备打开失败，请重新插拔后重试"
        return result, False
    try:
        result["endpoints"] = [hex(p[0]) for p in dev.list_pipes()]
        result["initialized"] = "0x82" in result["endpoints"]
        if not result["initialized"]:
            result["error"] = "设备缺少 0x82 端点，请先启动一次 Logic.exe 初始化设备"
    except Exception as e:
        result["error"] = occupied_hint(e)
        result["occupied"] = True
    finally:
        try:
            dev.close()
        except Exception:
            pass
    return result, bool(result["occupied"])


def signal_in_blob(blob: bytes) -> bool:
    """快速判断原始字节流中任意通道是否出现跳变。"""
    if len(blob) < 2:
        return False
    arr = np.frombuffer(blob, dtype=np.uint8)
    return bool(np.any(arr[1:] != arr[:-1]))


def save_capture(blob: bytes, rate_hz: int, name_hz: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mhz = name_hz.replace("MHz", "") if name_hz.endswith("MHz") else str(rate_hz // 1000000)
    fname = f"capture_{stamp}_{mhz}MHz.bin"
    path = os.path.join(CAPTURE_DIR, fname)
    with open(path, "wb") as fh:
        fh.write(blob)
    return path


def read_capture(cid: str) -> tuple[bytes, dict]:
    meta = STATE.get(cid)
    try:
        with open(meta["path"], "rb") as fh:
            return fh.read(), meta
    except OSError as e:
        raise ApiError(404, f"采集文件已不存在：{meta['path']}（{e}）")


def measure_channel(arr: np.ndarray, ch: int, rate_hz: int) -> dict:
    bits = ((arr >> ch) & 1).astype(np.uint8)
    n = len(bits)
    out = dict(channel=ch, edges=0, freq=0.0, duty=0.0,
               high_ratio=0.0, min_pulse=0, max_pulse=0)
    if n < 2:
        return out
    edges = int(np.count_nonzero(bits[1:] != bits[:-1]))
    transitions = np.flatnonzero(bits[1:] != bits[:-1]) + 1
    boundaries = np.concatenate(([0], transitions, [n]))
    runs = np.diff(boundaries)
    highs = bits[boundaries[:-1]]
    high_runs = runs[highs == 1]
    out["edges"] = edges
    out["high_ratio"] = round(float(np.count_nonzero(bits)) / n, 6)
    if len(high_runs):
        out["min_pulse"] = int(high_runs.min())
        out["max_pulse"] = int(high_runs.max())
    rising = np.flatnonzero((bits[1:] == 1) & (bits[:-1] == 0)) + 1
    falling = np.flatnonzero((bits[1:] == 0) & (bits[:-1] == 1)) + 1
    if rising.size >= 2:
        period = float(np.median(np.diff(rising)))
        if period > 0:
            out["freq"] = round(rate_hz / period, 2)
            if len(high_runs):
                duty = float(np.median(high_runs)) / period
                out["duty"] = round(min(max(duty, 0.0), 1.0), 6)
    return out


def safe_handler(fn):
    """统一把异常转成中文 JSON，绝不裸奔 500。"""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except ApiError as e:
            self.send_json({"ok": False, "error": e.message}, status=e.status)
        except Exception as e:
            log_line(f"异常 {self.command} {self.path}: {type(e).__name__}: {e}")
            self.send_json({"ok": False, "error": f"服务器内部错误：{e}"}, status=400)
    return wrapper


def json_body(self) -> dict:
    try:
        length = int(self.headers.get("Content-Length", "0"))
    except ValueError:
        raise ApiError(400, "请求体长度无效")
    if length <= 0:
        return {}
    if length > 8 * 1024 * 1024:
        raise ApiError(400, "请求体过大")
    raw = self.rfile.read(length)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ApiError(400, "请求体不是合法的 JSON")
    if not isinstance(obj, dict):
        raise ApiError(400, "请求体必须是 JSON 对象")
    return obj


def build_trigger(spec: dict):
    if not isinstance(spec, dict):
        raise ApiError(400, "trigger 必须是对象")
    ttype = str(spec.get("type", "edge")).lower()
    ch = check_channel(spec.get("channel", 0), "触发通道")
    try:
        if ttype in ("edge", "rising", "falling"):
            return trig.EdgeTrigger(ch, rising=(ttype != "falling"),
                                    count=int(spec.get("count", 1)))
        if ttype == "level":
            return trig.LevelTrigger(ch, level=int(spec.get("level", 1)),
                                     count=int(spec.get("count", 1)))
        if ttype in ("pulse", "pulsewidth", "pulse_width"):
            lo, hi = spec.get("min_samples"), spec.get("max_samples")
            return trig.PulseWidthTrigger(
                ch, min_samples=int(lo) if lo is not None else None,
                max_samples=int(hi) if hi is not None else None,
                polarity=str(spec.get("polarity", "high")))
    except (ValueError, TypeError) as e:
        raise ApiError(400, f"触发参数无效：{e}")
    raise ApiError(400, f"不支持的触发类型 {ttype!r}，可选 edge/level/pulse")


def decode_events(blob: bytes, meta: dict, protocol: str, params: dict) -> tuple[list, str]:
    rate = meta["rate_hz"]
    p = str(protocol).lower()
    try:
        if p in ("uart", "异步串口"):
            ch = check_channel(params.get("channel", 0))
            baud = int(params.get("baud", 115200))
            if baud <= 0:
                raise ApiError(400, "波特率必须为正整数")
            evs = decoder_uart.decode_uart(blob, rate, ch, baud)
        elif p in ("i2c",):
            scl = check_channel(params.get("scl", params.get("scl_channel", 1)), "SCL 通道")
            sda = check_channel(params.get("sda", params.get("sda_channel", 0)), "SDA 通道")
            evs = decoder_i2c.decode_i2c(blob, rate, scl, sda)
        elif p in ("spi",):
            sck = check_channel(params.get("sck", params.get("sck_channel", 1)), "SCK 通道")
            mosi = check_channel(params.get("mosi", params.get("mosi_channel", 2)), "MOSI 通道")
            cskw = dict(cpol=0, cpha=0)
            if params.get("cs") is not None:
                cskw["cs_ch"] = check_channel(params["cs"], "CS 通道")
            cskw["cpol"] = int(params.get("cpol", 0))
            cskw["cpha"] = int(params.get("cpha", 0))
            evs = decoder_spi.decode_spi(blob, rate, sck, mosi, **cskw)
        elif p in ("can",):
            ch = check_channel(params.get("channel", 0))
            bitrate = int(params.get("bitrate", 500000))
            evs = decoder_can.decode_can(blob, rate, ch, bitrate)
        else:
            raise ApiError(400, f"不支持的协议 {protocol!r}，可选 uart/i2c/spi/can")
    except ApiError:
        raise
    except Exception as e:
        raise ApiError(400, f"解码失败：{e}")
    out = []
    for ev in evs:
        data = ev.data
        if not isinstance(data, dict):
            data = {"value": data}
        out.append(dict(kind=str(ev.kind), start_sample=int(ev.start_sample),
                        end_sample=int(ev.end_sample),
                        data={k: (int(v) if isinstance(v, (np.integer, int)) else
                                  float(v) if isinstance(v, (np.floating, float)) else str(v))
                              for k, v in data.items()}))
    kinds: dict[str, int] = {}
    for ev in out:
        kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
    summary = "，".join(f"{k}×{v}" for k, v in kinds.items()) or "未解码出有效事件"
    return out, summary


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LogicAnalyzerWeb/1.0"

    def log_message(self, fmt, *args):
        pass  # 自己记日志，不用默认 stderr

    # -- 响应原语 -------------------------------------------------
    def send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_bytes(self, body: bytes, content_type: str, status: int = 200,
                   extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        t0 = time.monotonic()
        code_holder = {"code": 200}
        try:
            parts = urlsplit(self.path)
            route = unquote(parts.path)
            query = parse_qs(parts.query)
            if method == "GET":
                self._route_get(route, query)
            else:
                self._route_post(route, query)
        except ApiError as e:
            code_holder["code"] = e.status
            self.send_json({"ok": False, "error": e.message}, status=e.status)
        except Exception as e:
            code_holder["code"] = 400
            log_line(f"异常 {method} {self.path}: {type(e).__name__}: {e}")
            self.send_json({"ok": False, "error": f"服务器内部错误：{e}"}, status=400)
        finally:
            ms = (time.monotonic() - t0) * 1000
            log_line(f"{method} {self.path} -> {code_holder['code']} ({ms:.0f}ms)")

    def _route_get(self, route: str, query: dict) -> None:
        if route == "/":
            return self.handle_root()
        if route.startswith("/static/"):
            return self.handle_static(route[len("/static/"):])
        if route == "/api/status":
            return self.handle_status()
        if route.startswith("/api/data/"):
            return self.handle_data(route[len("/api/data/"):])
        if route.startswith("/api/measure/"):
            return self.handle_measure(route[len("/api/measure/"):], query)
        if route == "/api/open-folder":
            return self.handle_open_folder()
        if route == "/api/events":
            return self.handle_events()
        raise ApiError(404, f"找不到页面或接口：{route}")

    def _route_post(self, route: str, query: dict) -> None:
        if route == "/api/capture":
            return self.handle_capture()
        if route == "/api/capture/triggered":
            return self.handle_capture_triggered()
        if route == "/api/decode":
            return self.handle_decode()
        if route == "/api/save":
            return self.handle_save()
        raise ApiError(404, f"找不到接口：{route}")

    # -- 静态页面 -------------------------------------------------
    def handle_root(self):
        path = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                return self.send_bytes(fh.read(), "text/html; charset=utf-8")
        html = ("<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
                "<title>逻辑分析仪</title><body style=\"font-family:微软雅黑;text-align:center;"
                "padding-top:15vh\"><h1>后端已启动</h1><p>前端页面尚未就绪，"
                "请在 static 目录放置 index.html。</p></body></html>")
        return self.send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

    def handle_static(self, rel: str):
        if not rel or "\x00" in rel:
            raise ApiError(404, "文件不存在")
        rel = rel.replace("\\", "/")
        if ".." in rel.split("/"):
            raise ApiError(403, "禁止访问上级目录")
        ext = os.path.splitext(rel)[1].lower()
        if ext not in (".js", ".css", ".html", ".ico", ".png", ".svg", ".json"):
            raise ApiError(403, "不支持的静态文件类型")
        path = os.path.abspath(os.path.join(STATIC_DIR, rel))
        if not (path == STATIC_DIR or path.startswith(STATIC_DIR + os.sep)):
            raise ApiError(403, "禁止访问目录之外的文件")
        if not os.path.isfile(path):
            raise ApiError(404, f"静态文件不存在：{rel}")
        with open(path, "rb") as fh:
            body = fh.read()
        types = {".js": "application/javascript", ".css": "text/css",
                 ".html": "text/html", ".ico": "image/x-icon",
                 ".png": "image/png", ".svg": "image/svg+xml",
                 ".json": "application/json"}
        ctype = types[ext] + ("; charset=utf-8" if ext in (".js", ".css", ".html", ".json") else "")
        return self.send_bytes(body, ctype)

    @safe_handler
    def handle_status(self):
        dev, occupied = device_status()
        rates = [dict(hz=hz, name=name) for hz, _, name in cv.RATES]
        return self.send_json(dict(ok=True, device=dev, occupied=occupied,
                                   rates=rates, version=VERSION,
                                   signal_present=STATE.signal_present,
                                   capture_dir=CAPTURE_DIR))

    @safe_handler
    def handle_data(self, cid: str):
        blob, meta = read_capture(cid)
        return self.send_bytes(blob, "application/octet-stream",
                               extra={"X-Rate-Hz": str(meta["rate_hz"]),
                                      "X-Samples": str(meta["n_samples"])})

    @safe_handler
    def handle_open_folder(self):
        path = CAPTURE_DIR
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", path], close_fds=True)
            return self.send_json(dict(ok=True, path=path))
        except Exception as e:
            raise ApiError(400, f"打开文件夹失败：{e}")

    # -- 采集 -----------------------------------------------------
    def _acquire(self, hz: int, delay: int, seconds: float, name: str) -> tuple[bytes, float]:
        """独占设备采集：锁内开关设备，保证读线程退出、句柄释放。"""
        if not STATE.device_lock.acquire(blocking=False):
            raise ApiError(409, "设备正在采集中，请等待当前采集完成")
        dev = None
        try:
            STATE.emit("progress", value=0.05)
            try:
                dev = cv.open_dev()
            except Exception as e:
                raise ApiError(409, occupied_hint(e))
            if dev is None:
                raise ApiError(409, "未检测到设备，请检查 USB 连接")
            pipes = [p[0] for p in dev.list_pipes()]
            if cv.EP_DATA_IN not in pipes:
                raise ApiError(409, "设备缺少 0x82 端点，请先启动一次 Logic.exe 初始化设备")
            if STATE.inject_delay > 0:
                time.sleep(STATE.inject_delay)
            STATE.emit("progress", value=0.35)
            blob, elapsed = cv.capture_timed(dev, delay, seconds, n_readers=3)
            STATE.emit("progress", value=0.9)
            if not blob:
                raise ApiError(400, "没有收到采样数据，请检查设备连接后重试")
            return blob, elapsed
        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
            STATE.device_lock.release()

    @safe_handler
    def handle_capture(self):
        body = json_body(self)
        hz, delay, name = check_rate(body.get("rate_hz"))
        seconds = check_seconds(body.get("seconds", 1.0))
        blob, elapsed = self._acquire(hz, delay, seconds, name)
        # 设备命令后会持续输出，capture_timed 的读线程会多收 0.2s 预命令残留。
        # 只保留用户请求的时长窗口，保证 n_samples 与请求一致。
        want = int(round(hz * seconds))
        if len(blob) > want:
            blob = blob[:want]
        STATE.signal_present = signal_in_blob(blob)
        path = save_capture(blob, hz, name)
        cid = STATE.register(path, hz, len(blob), elapsed)
        # 达成率的分母必须和分子口径一致：blob 已裁成 hz*seconds，
        # 所以分母用 seconds 而不是 elapsed（后者含读线程启动与预命令等待，
        # 会算出 84% 这种误导性数字，让用户以为丢数据了）。
        achievement = round(len(blob) / max(seconds * hz, 1) * 100, 1)
        STATE.emit("progress", value=1.0)
        STATE.emit("done", id=cid)
        return self.send_json(dict(ok=True, id=cid, n_samples=len(blob),
                                   rate_hz=hz, elapsed=round(elapsed, 4),
                                   achievement=achievement, saved_path=path))

    @safe_handler
    def handle_capture_triggered(self):
        body = json_body(self)
        hz, delay, name = check_rate(body.get("rate_hz"))
        seconds = check_seconds(body.get("seconds", 1.0))
        trig_obj = build_trigger(body.get("trigger", {}))
        pre = float(body.get("pre_ratio", 0.2))
        if not 0.0 <= pre < 1.0:
            raise ApiError(400, "pre_ratio 必须在 0 到 1 之间")
        if not STATE.device_lock.acquire(blocking=False):
            raise ApiError(409, "设备正在采集中，请等待当前采集完成")
        dev = None
        try:
            STATE.emit("progress", value=0.05)
            try:
                dev = cv.open_dev()
            except Exception as e:
                raise ApiError(409, occupied_hint(e))
            if dev is None or cv.EP_DATA_IN not in [p[0] for p in dev.list_pipes()]:
                raise ApiError(409, "设备未就绪（缺 0x82），请先启动一次 Logic.exe 初始化设备")
            cap = tc.TriggeredCapture(dev, hz, trig_obj, pre)
            result = cap.run(seconds)
            blob = np.asarray(result.data, dtype=np.uint8).tobytes()
            elapsed = round(seconds, 4)
        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
            STATE.device_lock.release()
        if not blob:
            raise ApiError(400, "没有收到采样数据")
        STATE.signal_present = signal_in_blob(blob)
        path = save_capture(blob, hz, name)
        cid = STATE.register(path, hz, len(blob), elapsed,
                             found=result.found, trigger_offset=result.trigger_offset)
        STATE.emit("progress", value=1.0)
        STATE.emit("done", id=cid)
        return self.send_json(dict(ok=True, id=cid, n_samples=len(blob),
                                   rate_hz=hz, elapsed=elapsed, achievement=100.0,
                                   saved_path=path, found=bool(result.found),
                                   trigger_offset=result.trigger_offset))

    @safe_handler
    def handle_decode(self):
        body = json_body(self)
        cid = str(body.get("id", ""))
        blob, meta = read_capture(cid)
        protocol = body.get("protocol", "uart")
        params = body.get("params") or {}
        if not isinstance(params, dict):
            raise ApiError(400, "params 必须是对象")
        events, summary = decode_events(blob, meta, protocol, params)
        return self.send_json(dict(ok=True, events=events, summary=summary,
                                   count=len(events)))

    @safe_handler
    def handle_measure(self, cid: str, query: dict):
        blob, meta = read_capture(cid)
        arr = np.frombuffer(blob, dtype=np.uint8)
        window = None
        if "window" in query:
            try:
                window = json.loads(query["window"][0])
                if not (isinstance(window, list) and len(window) == 2):
                    raise ValueError
                start, end = int(window[0]), int(window[1])
                start = max(0, min(start, len(arr)))
                end = max(start, min(end, len(arr)))
                arr = arr[start:end]
            except Exception:
                raise ApiError(400, "window 参数格式应为 [start,end]")
        channels = [measure_channel(arr, ch, meta["rate_hz"]) for ch in range(8)]
        return self.send_json(dict(ok=True, channels=channels, n_samples=len(arr)))

    @safe_handler
    def handle_save(self):
        body = json_body(self)
        cid = str(body.get("id", ""))
        fmt = str(body.get("format", "csv")).lower()
        blob, meta = read_capture(cid)
        channels = body.get("channels")
        if channels is not None and not isinstance(channels, list):
            raise ApiError(400, "channels 必须是数组")
        ext = {"csv": ".csv", "vcd": ".vcd", "bin": ".bin"}.get(fmt)
        if ext is None:
            raise ApiError(400, "format 只能是 csv、vcd 或 bin")
        base = os.path.splitext(os.path.basename(meta["path"]))[0]
        path = os.path.join(CAPTURE_DIR, base + ext)
        try:
            if fmt == "csv":
                exporter.export_csv(path, blob, meta["rate_hz"], channels)
            elif fmt == "vcd":
                exporter.export_vcd(path, blob, meta["rate_hz"], channels)
            else:
                exporter.export_binary(path, blob)
        except Exception as e:
            raise ApiError(400, f"导出失败：{e}")
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise ApiError(400, "导出文件为空")
        return self.send_json(dict(ok=True, path=path))

    @safe_handler
    def handle_events(self):
        q = STATE.add_listener()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(b"data: {\"type\":\"hello\"}\n\n")
            self.wfile.flush()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    item = q.get(timeout=1.0)
                except queue.Empty:
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    continue
                self.wfile.write(("data: " + json.dumps(item, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
        finally:
            STATE.remove_listener(q)


def create_server(host: str = "127.0.0.1", port: int = 0,
                  inject_delay: float = 0.0) -> ThreadingHTTPServer:
    STATE.inject_delay = float(inject_delay)
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def main() -> int:
    srv = create_server(port=8421)
    port = srv.server_address[1]
    print(f"逻辑分析仪后端已启动，端口 {port}")
    log_line(f"服务启动 127.0.0.1:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
