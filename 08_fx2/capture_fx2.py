"""Saleae Logic (FX2 clone, 0925:3881) streaming capture -- pure ctypes WinUSB.

Protocol, cross-checked against three independent sources:

  1. keesj/saleae-logic-libusb (BSD-3, slogic.c) -- targets exactly 0925:3881:
       COMMAND_OUT_ENDPOINT       = 0x01
       COMMAND_IN_ENDPOINT        = 0x81
       STREAMING_DATA_IN_ENDPOINT = 0x82        <-- sample data, NOT 0x81
       start = bulk write {0x01, sample_delay} to EP 0x01
       defaults: 4 KiB buffers, 4 concurrent transfers, 1000 ms timeout

  2. sigrok/libsigrok fx2lafw (protocol.c): data endpoint is `2 | LIBUSB_ENDPOINT_IN`
     (= 0x82), and the delay formula is `48MHz / rate - 1` -- identical to what we
     recovered from Logic.exe.

  3. Our own disassembly of Logic.exe (RVA 0x14b3254): the official client builds
     `buffer = {0x01, divider - 1}` with divider = 48000000 / rate, length 2,
     then calls Write. For 200 kHz that is 0xEF -- matching the open-source table.

Important ordering note: the device only starts streaming once a read is already
pending on 0x82. keesj's driver instead waited for 200 timeouts before sending
the start command, which its own TODO file lists as a known hang. We therefore
start the reader thread FIRST and send the command second -- the same order
sigrok uses (submit transfers, then CMD_START).

The official client also runs every byte through a stateful obfuscator
(Logic.exe 0x322250) before writing. The hardware does not require it: the
open-source drivers send plaintext commands and the device streams fine. So we
send plaintext. The obfuscator is fully documented in 06_disasm/ if ever needed.

Usage:
    python -I capture_fx2.py --list-rates
    python -I capture_fx2.py --rate 1000000 --seconds 3 --out wave.bin
    python -I capture_fx2.py --rate 1000000 --seconds 3 --probe   # try every endpoint
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "03_host"))
import winusb  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EP_CMD_OUT = 0x01
EP_CMD_IN = 0x81
EP_DATA_IN = 0x88   # 实测本机端点是 0x88，不是开源文档说的 0x82
EP_DATA_OUT = 0x06

READ_CHUNK = 4096          # keesj DEFAULT_TRANSFER_BUFFER_SIZE
ERR_TIMEOUT = 121          # ERROR_SEM_TIMEOUT

SAMPLE_RATES = [
    (24000000, 1, "24MHz"),
    (16000000, 2, "16MHz"),
    (12000000, 3, "12MHz"),
    (8000000, 5, "8MHz"),
    (4000000, 11, "4MHz"),
    (2000000, 24, "2MHz"),
    (1000000, 47, "1MHz"),
    (500000, 95, "500kHz"),
    (250000, 191, "250kHz"),
    (200000, 239, "200kHz"),
]
RATE_BY_HZ = {hz: (d, name) for hz, d, name in SAMPLE_RATES}


def list_rates():
    print("采样率表（delay 来自 keesj/saleae-logic-libusb，与 Logic.exe 反汇编 48MHz/rate-1 互验）")
    print("  速率        delay  hex  48MHz/rate-1  一致?")
    for hz, d, name in SAMPLE_RATES:
        calc = (48000000 // hz) - 1
        mark = "是" if calc == d else f"否(算出{calc})"
        print(f"  {name:8s} {d:6d}  0x{d:02x}  {calc:11d}  {mark}")
    print()
    print("注：2MHz 一处差 1（表=24, 算=23），两次实现取舍不同；两值都会试。")


def open_device():
    devs = winusb.enumerate_devices()
    if not devs:
        print("未发现设备（0925:3881）。")
        return None
    dev = winusb.SaleaeDevice(devs[0]["path"])
    dev.open()
    for pipe in (EP_CMD_OUT, EP_CMD_IN, EP_DATA_IN):
        for pol, val in ((winusb.PIPE_TRANSFER_TIMEOUT, 1000),
                         (winusb.RAW_IO, 1),
                         (winusb.IGNORE_SHORT_PACKETS, 1)):
            try:
                dev.set_pipe_policy(pipe, pol, val)
            except Exception:
                pass
    return dev


class Reader(threading.Thread):
    """Continuously read EP 0x82 in the background.

    Started BEFORE the start command is written, so a read is already pending
    when the device begins streaming.
    """

    def __init__(self, dev, pipe):
        super().__init__(daemon=True)
        self.dev = dev
        self.pipe = pipe
        self.stop_flag = threading.Event()
        self.data = bytearray()
        self.reads = 0
        self.errors = []
        self.first_at = None

    def run(self):
        while not self.stop_flag.is_set():
            try:
                chunk = self.dev.read_pipe(self.pipe, READ_CHUNK, timeout_ms=500)
                if chunk:
                    if self.first_at is None:
                        self.first_at = time.monotonic()
                    self.data += chunk
                    self.reads += 1
            except Exception as e:
                msg = str(e)
                if str(ERR_TIMEOUT) in msg:
                    continue
                self.errors.append(msg)
                if len(self.errors) > 3:
                    break

    def stop(self):
        self.stop_flag.set()


def probe_all_endpoints(dev, delay, seconds_each=2.0):
    """Try every plausible data endpoint so a dead end is ruled out fast."""
    results = {}
    for pipe in (EP_DATA_IN, EP_CMD_IN, 0x86, 0x02):
        print(f"\n--- 试探端点 0x{pipe:02x} ---")
        rd = Reader(dev, pipe)
        rd.start()
        time.sleep(0.3)                       # let the read go pending first
        try:
            n = dev.write_pipe(EP_CMD_OUT, bytes([0x01, delay]), timeout_ms=1000)
            print(f"    启动命令 01{delay:02x} -> EP1 OUT ({n} 字节)")
        except Exception as e:
            print(f"    启动命令失败: {str(e)[-40:]}")
        time.sleep(seconds_each)
        rd.stop()
        rd.join(timeout=2)
        results[pipe] = len(rd.data)
        preview = bytes(rd.data[:16]).hex()
        print(f"    0x{pipe:02x}: {len(rd.data)} 字节 / {rd.reads} 次读取  前16B={preview}")
    return results


def capture(dev, delay, seconds, pipe=EP_DATA_IN):
    rd = Reader(dev, pipe)
    rd.start()
    print(f"读线程已在 0x{pipe:02x} 上挂起等待…")
    time.sleep(0.3)

    cmd = bytes([0x01, delay & 0xFF])
    try:
        n = dev.write_pipe(EP_CMD_OUT, cmd, timeout_ms=1000)
        print(f"启动命令 {cmd.hex()} -> EP1 OUT 完成（{n} 字节）")
    except Exception as e:
        print(f"启动命令失败: {str(e)[-50:]}")
        rd.stop()
        rd.join(timeout=2)
        return b"", rd

    print(f"采集中 {seconds}s …")
    time.sleep(seconds)
    rd.stop()
    rd.join(timeout=3)
    return bytes(rd.data), rd


def analyze(data, seconds, rate):
    print(f"\n===== 结果 =====")
    print(f"总字节 {len(data)}  ({len(data)/1024:.1f} KiB)")
    if not data:
        return False
    expected = rate * seconds
    print(f"理论样本数 {int(expected)}，实际 {len(data)}  → 占比 {len(data)/expected*100:.1f}%")
    print(f"前 32 字节: {data[:32].hex()}")

    uniq = sorted(set(data[:8192]))
    print(f"前 8K 字节里的不同取值: {len(uniq)} 种")
    print(f"  取值: {[hex(x) for x in uniq[:16]]}{' …' if len(uniq) > 16 else ''}")

    if len(data) >= 2:
        edges = sum(1 for a, b in zip(data, data[1:]) if a != b)
        print(f"相邻字节变化次数: {edges} / {len(data)-1}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=1000000)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--out", default="wave.bin")
    ap.add_argument("--list-rates", action="store_true")
    ap.add_argument("--probe", action="store_true", help="逐个试探数据端点")
    ap.add_argument("--delay-alt", action="store_true",
                    help="用 48MHz/rate 而非表值（只差 2MHz 档）")
    args = ap.parse_args()

    if args.list_rates:
        list_rates()
        return 0

    if args.rate not in RATE_BY_HZ:
        print(f"不支持的采样率 {args.rate}；用 --list-rates 查看。")
        return 2
    delay, name = RATE_BY_HZ[args.rate]
    if args.delay_alt:
        delay = 48000000 // args.rate
    print(f"采样率 {name}  delay={delay} (0x{delay:02x})")

    dev = open_device()
    if dev is None:
        return 2
    try:
        speed = dev.query_speed()
        print(f"设备已打开  速度={speed}")

        # Firmware sanity check: a single 0x05 should beacknowledged on 0x81.
        try:
            dev.write_pipe(EP_CMD_OUT, b"\x05", timeout_ms=500)
            ack = dev.read_pipe(EP_CMD_IN, 1, timeout_ms=500)
            print(f"固件探测 0x05 -> 应答 {ack.hex()}（固件已加载）")
        except Exception as e:
            print(f"固件探测 0x05 无应答: {str(e)[-40:]}")

        if args.probe:
            res = probe_all_endpoints(dev, delay)
            best = max(res, key=res.get)
            print(f"\n最有希望的端点: 0x{best:02x}（{res[best]} 字节）")
            return 0 if res[best] else 1

        data, rd = capture(dev, delay, args.seconds)
        if rd.errors:
            print(f"读线程异常 {len(rd.errors)} 条，首条: {rd.errors[0][-60:]}")

        ok = analyze(data, args.seconds, args.rate)
        if ok:
            with open(args.out, "wb") as fh:
                fh.write(data)
            print(f"\n已保存 {args.out}")
            return 0
        print("\n没采到数据。下一步：")
        print("  1) 先试 --probe 逐个端点")
        print("  2) 再试 --delay-alt（2MHz 档差 1）")
        print("  3) 都失败则考虑 Control 传输路线（sigrok CMD_START=0xb1）")
        return 1
    finally:
        try:
            dev.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
