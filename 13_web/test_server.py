# -*- coding: utf-8 -*-
"""13_web 后端自测：用 urllib 打真实 HTTP 请求（无需 pytest/第三方客户端）。"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)
import server as srv

BASE = ""


def http(method: str, path: str, body: dict | None = None):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jbody(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global BASE
        cls.server = srv.create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        BASE = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.last_id = None
        cls.last_samples = None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=10)

    def test_01_status(self):
        code, _, raw = http("GET", "/api/status")
        self.assertEqual(code, 200)
        obj = jbody(raw)
        self.assertTrue(obj["ok"])
        self.assertIn("device", obj)
        self.assertIn("occupied", obj)
        self.assertIn("signal_present", obj)
        self.assertEqual(len(obj["rates"]), 10)

    def test_02_capture(self):
        code, _, raw = http("POST", "/api/capture", dict(rate_hz=1000000, seconds=0.5))
        self.assertEqual(code, 200, raw.decode("utf-8", "replace"))
        obj = jbody(raw)
        self.assertTrue(obj["ok"])
        n = obj["n_samples"]
        self.assertTrue(400000 <= n <= 600000, f"样本数 {n} 不在 40 万~60 万")
        self.assertTrue(os.path.isfile(obj["saved_path"]), obj["saved_path"])
        self.assertEqual(os.path.getsize(obj["saved_path"]), n)
        type(self).last_id = obj["id"]
        type(self).last_samples = n

    def test_03_data_binary(self):
        cid = type(self).last_id
        self.assertIsNotNone(cid)
        code, headers, raw = http("GET", f"/api/data/{cid}")
        self.assertEqual(code, 200)
        self.assertIn("application/octet-stream", headers.get("Content-Type", ""))
        self.assertEqual(len(raw), type(self).last_samples)

    def test_04_invalid_rate(self):
        code, _, raw = http("POST", "/api/capture", dict(rate_hz=12345, seconds=0.5))
        self.assertEqual(code, 400)
        obj = jbody(raw)
        self.assertFalse(obj["ok"])
        self.assertIn("采样率", obj["error"])

    def test_05_concurrent_conflict(self):
        """用后台真实 HTTP 请求 + 注入延迟制造并发，不靠慢速设备采集。"""
        old = srv.STATE.inject_delay
        srv.STATE.inject_delay = 2.0
        results = {}
        try:
            def slow():
                try:
                    results["first"] = http("POST", "/api/capture",
                                            dict(rate_hz=1000000, seconds=0.2))
                except Exception as e:
                    results["first_err"] = e
            t = threading.Thread(target=slow, daemon=True)
            t.start()
            import time
            time.sleep(0.5)
            results["second"] = http("POST", "/api/capture",
                                     dict(rate_hz=1000000, seconds=0.2))
            t.join(timeout=30)
        finally:
            srv.STATE.inject_delay = old
        self.assertIn("first", results)
        code2, _, raw2 = results["second"]
        self.assertEqual(code2, 409, f"第二个请求应 409，实际 {code2}: {raw2[:200]}")
        self.assertIn("采集", jbody(raw2)["error"])

    def test_06_decode_uart(self):
        cid = type(self).last_id
        self.assertIsNotNone(cid)
        code, _, raw = http("POST", "/api/decode",
                            dict(id=cid, protocol="uart",
                                 params=dict(channel=0, baud=115200)))
        self.assertEqual(code, 200, raw.decode("utf-8", "replace"))
        obj = jbody(raw)
        self.assertTrue(obj["ok"])
        self.assertIsInstance(obj["events"], list)
        self.assertIn("summary", obj)

    def test_07_measure(self):
        cid = type(self).last_id
        self.assertIsNotNone(cid)
        code, _, raw = http("GET", f"/api/measure/{cid}")
        self.assertEqual(code, 200)
        obj = jbody(raw)
        self.assertEqual(len(obj["channels"]), 8)
        ch0 = obj["channels"][0]
        self.assertEqual(ch0["channel"], 0)
        if ch0["edges"] > 0:
            print("  [测量模式] 有信号：CH0 跳变数 =", ch0["edges"])
            self.assertTrue(49000 <= ch0["freq"] <= 51000,
                            f"CH0 频率 {ch0['freq']}")
        else:
            print("  [测量模式] 无信号：CH0 无跳变（信号源可能断开），"
                  "仅验证结构正确，不验证频率")
            for key in ("channel", "edges", "freq", "duty", "high_ratio",
                        "min_pulse", "max_pulse"):
                self.assertIn(key, ch0)

    def test_08_save_csv(self):
        cid = type(self).last_id
        self.assertIsNotNone(cid)
        code, _, raw = http("POST", "/api/save", dict(id=cid, format="csv", channels=[0]))
        self.assertEqual(code, 200, raw.decode("utf-8", "replace"))
        obj = jbody(raw)
        self.assertTrue(obj["ok"])
        self.assertTrue(os.path.isfile(obj["path"]))
        self.assertGreater(os.path.getsize(obj["path"]), 0)

    def test_09_path_traversal(self):
        code, _, _ = http("GET", "/static/../server.py")
        self.assertIn(code, (403, 404))

    def test_10_404_json(self):
        code, _, raw = http("GET", "/api/not-exist")
        self.assertEqual(code, 404)
        obj = jbody(raw)
        self.assertFalse(obj["ok"])
        self.assertIn("error", obj)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ServerTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"ALL TESTS PASSED ({result.testsRun} 个用例)")
    else:
        raise SystemExit(1)
