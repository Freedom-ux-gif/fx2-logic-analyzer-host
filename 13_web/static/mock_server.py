#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯标准库 mock 后端：合成 50 kHz 方波，实现前端契约中的全部 API。
启动: python -I mock_server.py --port 8421
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))

DATA = {}
STATE = {"value": 0.0, "done_id": None, "revision": 0}
LOCK = threading.Lock()
RATES = [
    (24000000, "24M"), (16000000, "16M"), (12000000, "12M"), (8000000, "8M"),
    (4000000, "4M"), (2000000, "2M"), (1000000, "1M"), (500000, "500k"),
    (250000, "250k"), (200000, "200k"),
]


def synth(rate_hz, seconds, trigger=None):
    """生成合成采样数据：CH0 = 50 kHz 占空比 0.5 方波，其余通道为分频方波。"""
    n = max(1, int(rate_hz * seconds))
    n = min(n, 8_000_000)  # mock 上限，避免占满内存
    half = max(1.0, rate_hz / 100000.0)
    buf = bytearray(n)
    for i in range(n):
        v = 0
        # CH0: 50 kHz -> 周期 rate/50000 样本
        per0 = max(2.0, rate_hz / 50000.0)
        if (i % per0) < per0 / 2:
            v |= 1
        if (i % (per0 * 4)) < per0 * 2:
            v |= 2
        if (i % (per0 * 8)) < per0 * 4:
            v |= 4
        if (i % 97) == 0:
            v |= 8
        buf[i] = v
    return bytes(buf)


def measure(data, rate):
    """真实计算各通道边沿/频率/占空比/脉宽。"""
    n = len(data)
    out = []
    for ch in range(8):
        bit = 1 << ch
        edges = 0
        last = (data[0] >> ch) & 1 if n else 0
        highs = 0
        widths = []
        run = 1
        for i in range(1, n):
            cur = (data[i] >> ch) & 1
            if cur:
                highs += 1
            if cur != last:
                edges += 1
                widths.append(run)
                run = 1
                last = cur
            else:
                run += 1
        if widths:
            widths.append(run)
        secs = n / float(rate)
        freq = edges / (2.0 * secs) if secs else 0.0
        duty = highs / float(n) if n else 0.0
        out.append({
            "channel": ch, "edges": edges,
            "freq": round(freq, 3), "duty": round(duty, 5),
            "high_ratio": round(duty, 5),
            "min_pulse": (min(widths) / float(rate) if widths else 0.0),
            "max_pulse": (max(widths) / float(rate) if widths else 0.0),
        })
    return out


def fake_events(proto, rate):
    periods = {"uart": 160, "i2c": 90, "spi": 60, "can": 200}
    p = periods.get(proto, 100)
    kinds = {
        "uart": ["start", "data", "data", "parity", "stop"],
        "i2c": ["start", "addr", "ack", "data", "stop"],
        "spi": ["cs_low", "byte", "byte", "cs_high"],
        "can": ["sof", "id", "data", "crc", "eof"],
    }[proto]
    evs = []
    for i in range(8):
        kind = kinds[i % len(kinds)]
        evs.append({
            "kind": kind,
            "start_sample": 1000 + i * p,
            "end_sample": 1000 + i * p + p - 1,
            "data": ("0x%02X" % ((i * 17 + 0x41) & 0xFF)) if kind in ("data", "byte", "addr", "id") else "",
        })
    return evs


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[mock] " + (fmt % args), flush=True)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, obj)

    def _err(self, msg, code=400):
        self._json({"ok": False, "error": msg}, code)

    def _body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as ex:
            raise ValueError("请求体不是合法 JSON：%s" % ex)

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/api/status":
            self._json({
                "ok": True,
                "device": {"present": True, "initialized": True,
                           "endpoints": ["0x1", "0x81", "0x82", "0x6"]},
                "rates": [{"hz": hz, "name": name} for hz, name in RATES],
                "version": "mock-1.0",
            })
        elif path.startswith("/api/data/"):
            cid = path[len("/api/data/"):]
            if cid not in DATA:
                return self._err("采集 ID 不存在：%s" % cid, 404)
            blob = DATA[cid]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
        elif path.startswith("/api/measure/"):
            cid = path[len("/api/measure/"):]
            if cid not in DATA:
                return self._err("采集 ID 不存在：%s" % cid, 404)
            self._json({"ok": True, "channels": measure(DATA[cid], META[cid]["rate_hz"])})
        elif path == "/api/open-folder":
            self._json({"ok": True, "path": os.path.join(HERE, "captures")})
        elif path == "/api/events":
            self._sse()
        else:
            self._static(path)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        with LOCK:
            start_rev = STATE["revision"]
        self.wfile.write(b'data: {"type":"progress","value":0.0}\n\n')
        self.wfile.flush()
        for _ in range(600):
            with LOCK:
                rev = STATE["revision"]
                val = STATE["value"]
                done = STATE["done_id"]
            if rev != start_rev:
                self.wfile.write(("data: %s\n\n" % json.dumps(
                    {"type": "progress", "value": val})).encode())
                self.wfile.flush()
                start_rev = rev
            if done:
                self.wfile.write(("data: %s\n\n" % json.dumps(
                    {"type": "done", "id": done})).encode())
                self.wfile.flush()
                return
            time.sleep(0.05)
        self.wfile.write(b'data: {"type":"progress","value":1.0}\n\n')
        self.wfile.flush()

    def _static(self, path):
        if path in ("/", "/index.html"):
            name = "index.html"
        else:
            name = os.path.basename(path)
        if name not in ("index.html", "style.css", "app.js", "selftest.html", "README-frontend.md"):
            return self._err("文件不存在", 404)
        full = os.path.join(HERE, name)
        if not os.path.isfile(full):
            return self._err("文件不存在", 404)
        with open(full, "rb") as f:
            body = f.read()
        ct = "text/html; charset=utf-8" if name.endswith(".html") else (
            "text/css; charset=utf-8" if name.endswith(".css") else (
                "application/javascript; charset=utf-8" if name.endswith(".js") else "text/plain; charset=utf-8"))
        self._send(200, body, ct)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body_json()
        except ValueError as ex:
            return self._err(str(ex))
        if path == "/api/capture":
            return self._capture(body)
        if path == "/api/capture/triggered":
            return self._capture(body, triggered=True)
        if path == "/api/decode":
            cid = body.get("id")
            if cid not in DATA:
                return self._err("采集 ID 不存在：%s" % cid, 404)
            proto = body.get("protocol", "uart")
            if proto not in ("uart", "i2c", "spi", "can"):
                return self._err("不支持的协议：" + str(proto))
            evs = fake_events(proto, META[cid]["rate_hz"])
            return self._json({"ok": True, "events": evs,
                               "summary": "%s: %d 条" % (proto, len(evs))})
        if path == "/api/save":
            cid = body.get("id")
            if cid not in DATA:
                return self._err("采集 ID 不存在：%s" % cid, 404)
            fmt = body.get("format", "csv")
            out = os.path.join(HERE, "captures", "%s.%s" % (cid, fmt))
            return self._json({"ok": True, "path": out})
        return self._err("未知接口：" + path, 404)

    def _capture(self, body, triggered=False):
        global META
        try:
            rate = int(body.get("rate_hz", 1000000))
            seconds = float(body.get("seconds", 1))
        except (TypeError, ValueError):
            return self._err("rate_hz / seconds 参数无效")
        if rate <= 0 or seconds <= 0:
            return self._err("rate_hz / seconds 必须为正数")
        if trigger := body.get("trigger"):
            if not isinstance(trigger, dict):
                return self._err("trigger 必须为对象")
        with LOCK:
            STATE["value"] = 0.0
            STATE["done_id"] = None
            STATE["revision"] += 1
        t0 = time.time()
        data = synth(rate, seconds)
        for pct in (0.25, 0.5, 0.75, 1.0):
            time.sleep(0.08)
            with LOCK:
                STATE["value"] = pct
                STATE["revision"] += 1
        cid = "cap_%d" % int(time.time() * 1000)
        DATA[cid] = data
        META[cid] = {"rate_hz": rate, "seconds": seconds}
        out = os.path.join(HERE, "captures", cid + ".bin")
        with LOCK:
            STATE["value"] = 1.0
            STATE["done_id"] = cid
            STATE["revision"] += 1
        res = {
            "ok": True, "id": cid, "n_samples": len(data), "rate_hz": rate,
            "elapsed": round(time.time() - t0, 4),
            "achievement": "50 kHz 方波 · CH0",
            "saved_path": out,
        }
        if triggered:
            res["found"] = True
            res["trigger_offset"] = 1000
        return self._json(res)


META = {}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8421)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("mock server on http://127.0.0.1:%d/" % args.port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
