"""Saleae Logic (0925:3881) capture -- VERIFIED WORKING 2026-11-25.

Verified against a real 8 kHz square wave from an oscilloscope:

    delay  nominal     main_run  measured
        3  12 MHz          750    8000 Hz
        5   8 MHz          500    8000 Hz
       11   4 MHz          250    8000 Hz
       47   1 MHz           63    7937 Hz  (quantisation)

Prerequisites discovered the hard way
-------------------------------------
1. Run Logic.exe ONCE after plugging the device in, then close it.
   That reconfigures the device: endpoints change from
       (uninitialised)  0x01 0x81 0x02 0x04 0x86 0x88
   to  (ready)          0x01 0x81 0x82 0x06          <- standard layout
   Without this, EP 0x82 does not exist and every read fails with 121.
   Note the alt setting is 0 in the ready state (not 1).

2. The command MUST be obfuscated. Plaintext {0x01, delay} writes fine but
   the device stays silent. The stateful obfuscator recovered from Logic.exe
   (0x322250, see 06_disasm/) turns {0x01, 0x2f} into {0xd5, 0x8e}, and only
   then does data appear.

3. Sample data arrives on EP 0x82 (bulk IN). EP 0x81 only carries the 1-byte
   command acknowledgement.

4. Each byte is 8 channels. The test signal landed on bit0, so for this clone
   CH1 is NOT bit7 as sigrok documents -- use bit0-based channel numbering or
   verify per board.

Usage:
    python -I capture_verified.py --delay 5 --seconds 2 --out wave.bin
    python -I capture_verified.py --rate 1000000 --seconds 2 --freq
"""
import argparse
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "03_host"))
import winusb  # noqa: E402

if sys.stdout is not None:   # PyInstaller --noconsole 下 sys.stdout 为 None
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EP_CMD_OUT = 0x01
EP_CMD_IN = 0x81
EP_DATA_IN = 0x82

RATES = [
    (24000000, 1, "24MHz"), (16000000, 2, "16MHz"), (12000000, 3, "12MHz"),
    (8000000, 5, "8MHz"), (4000000, 11, "4MHz"), (2000000, 24, "2MHz"),
    (1000000, 47, "1MHz"), (500000, 95, "500kHz"), (250000, 191, "250kHz"),
    (200000, 239, "200kHz"),
]
BY_HZ = {hz: (d, n) for hz, d, n in RATES}


def obfuscate(plain: bytes) -> bytes:
    """Logic.exe's stateful byte obfuscator (RVA 0x322250), fully reversed.

    A = previous cipher byte (init 0x54), B = previous plaintext (init 0x9b).
    Verified: enc(01 03) = d5 e2 (= device's own 0x58 reply),
              enc(01 05) = d5 d4, enc(7d 55) = 61 d4 (official capture).
    """
    out, A, B = [], 0x54, 0x9B
    for p in plain:
        t = A ^ p
        t ^= 0x2B
        t = (t - 5) & 0xFF
        t ^= 0x35
        t = (t - 0x39) & 0xFF
        t ^= B
        t ^= 0x5A
        t = (t + 0x50) & 0xFF
        t ^= 0x38
        t = (t - 0x45) & 0xFF
        out.append(t)
        B, A = p, t
    return bytes(out)


def open_dev():
    devs = winusb.enumerate_devices()
    if not devs:
        return None
    d = winusb.SaleaeDevice(devs[0]["path"])
    d.open()
    for pipe in (EP_CMD_OUT, EP_CMD_IN, EP_DATA_IN):
        for pol, val in ((winusb.PIPE_TRANSFER_TIMEOUT, 1000),
                         (winusb.RAW_IO, 1),
                         (winusb.IGNORE_SHORT_PACKETS, 1)):
            try:
                d.set_pipe_policy(pipe, pol, val)
            except Exception:
                pass
    return d


def capture(dev, delay, seconds):
    """Start reader first, then send the obfuscated start command."""
    chunks = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                b = dev.read_pipe(EP_DATA_IN, 65536, timeout_ms=500)
                if b:
                    chunks.append(b)
            except Exception as e:
                if "121" not in str(e):
                    break

    # Drain stale bytes left over from earlier captures.
    for _ in range(6):
        try:
            dev.read_pipe(EP_DATA_IN, 65536, timeout_ms=120)
        except Exception:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(0.25)

    cmd = obfuscate(bytes([0x01, delay & 0xFF]))
    dev.write_pipe(EP_CMD_OUT, cmd, timeout_ms=1000)

    time.sleep(seconds)
    stop.set()
    t.join(timeout=3)
    return b"".join(chunks)


def capture_mt(dev, delay, seconds, n_readers=2, chunk=65536):
    """Multi-reader capture -- REQUIRED above 4 MHz.

    A single synchronous reader loses samples at 8 MHz and above: the gap
    between one read_pipe() returning and the next starting is long enough for
    the device FIFO to overrun. Measured on this board (2 s target):

        rate    1 reader   2 readers
        4 MHz     25-100%      100%
        8 MHz       0.5%       100%
       12 MHz       0.4%       100%

    So two readers take turns draining 0x82 and the FIFO never fills.

    Returns bytes. Note the throughput ceiling still belongs to the device/USB
    path, not to Python: above ~12 MB/s this plateaus.
    """
    chunks = []
    lock = threading.Lock()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                b = dev.read_pipe(EP_DATA_IN, chunk, timeout_ms=400)
                if b:
                    with lock:
                        chunks.append(b)
            except Exception as e:
                if "121" not in str(e):
                    break

    for _ in range(8):
        try:
            dev.read_pipe(EP_DATA_IN, 65536, timeout_ms=100)
        except Exception:
            pass

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(n_readers)]
    for t in threads:
        t.start()
    time.sleep(0.2)

    dev.write_pipe(EP_CMD_OUT, obfuscate(bytes([0x01, delay & 0xFF])), timeout_ms=1000)

    time.sleep(seconds)
    stop.set()
    for t in threads:
        t.join(timeout=3)
    with lock:
        return b"".join(chunks)


def capture_timed(dev, delay, seconds, n_readers=3):
    """Same as capture_mt but also reports how long data actually flowed.

    capture_mt's wall time includes thread startup and the drain phase, which
    made 12 MHz look like 58% of nominal. Measuring the data window separately
    gives the honest achieved rate:

        delay  nominal   achieved
           11    4 MHz      101%
            5    8 MHz     100.5%
            3   12 MHz      68%   <- real ceiling on this machine

    Returns (bytes, elapsed_seconds).
    """
    chunks = []
    lock = threading.Lock()
    stop = threading.Event()
    state = {"first": None, "last": None}

    def reader():
        while not stop.is_set():
            try:
                b = dev.read_pipe(EP_DATA_IN, 65536, timeout_ms=400)
                if b:
                    now = time.monotonic()
                    with lock:
                        if state["first"] is None:
                            state["first"] = now
                        state["last"] = now
                        chunks.append(b)
            except Exception as e:
                if "121" not in str(e):
                    break

    for _ in range(8):
        try:
            dev.read_pipe(EP_DATA_IN, 65536, timeout_ms=100)
        except Exception:
            pass

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(n_readers)]
    for t in threads:
        t.start()
    time.sleep(0.2)

    t_send = time.monotonic()
    dev.write_pipe(EP_CMD_OUT, obfuscate(bytes([0x01, delay & 0xFF])), timeout_ms=1000)
    time.sleep(seconds)
    stop.set()
    for t in threads:
        t.join(timeout=3)
    with lock:
        data = b"".join(chunks)
        if state["first"] is not None and state["last"] is not None:
            elapsed = max(state["last"] - state["first"], 1e-6)
        else:
            elapsed = time.monotonic() - t_send
    return data, elapsed



def bit_freq(data: np.ndarray, bit: int, rate: int):
    """Return (frequency_hz, main_run_len, duty) for one channel bit."""
    b = ((data >> bit) & 1).astype(np.uint8)
    if len(b) < 100:
        return None
    b = b[len(b) // 5:]                     # drop possibly-stale head
    runs, cur, n = [], int(b[0]), 1
    for v in b[1:]:
        if v == cur:
            n += 1
        else:
            runs.append(n)
            cur, n = int(v), 1
    runs.append(n)
    if not runs:
        return None
    counts = {}
    for r in runs:
        counts[r] = counts.get(r, 0) + 1
    main = max(counts, key=counts.get)
    hi = sum(r for v, r in zip(b, runs * 2) if v == 1) if False else b.sum()
    duty = b.sum() / len(b)
    return rate / (2 * main), main, duty, len(runs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=int, default=None)
    ap.add_argument("--rate", type=int, default=None)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--out", default="wave.bin")
    ap.add_argument("--freq", action="store_true", help="print per-bit frequency")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for hz, d, n in RATES:
            print(f"  {n:8s} delay={d:3d} (0x{d:02x})")
        return 0

    if args.delay is not None:
        delay = args.delay
        rate = next((hz for hz, d, _ in RATES if d == delay), 0)
    elif args.rate is not None:
        if args.rate not in BY_HZ:
            print(f"unsupported rate {args.rate}; use --list")
            return 2
        delay, _ = BY_HZ[args.rate]
        rate = args.rate
    else:
        delay, rate = 47, 1000000
    print(f"delay={delay} (0x{delay:02x})  nominal={rate} Hz")
    print(f"start command: plaintext 01{delay:02x} -> wire {obfuscate(bytes([0x01,delay])).hex()}")

    dev = open_dev()
    if dev is None:
        print("no device found")
        return 2
    try:
        print(f"alt={dev.alt_setting}  speed={dev.query_speed()}")
        pipes = [hex(p) for p, _, _, _ in dev.list_pipes()]
        print(f"pipes={pipes}")
        if "0x82" not in pipes:
            print("\n⚠ EP 0x82 missing -- device not initialised.")
            print("  Run Logic.exe once after plugging in, close it, then retry.")
            return 3

        blob = capture(dev, delay, args.seconds)
        if not blob:
            print("\nno data received")
            return 1

        data = np.frombuffer(blob, dtype=np.uint8)
        print(f"\ncaptured {len(data)} samples ({len(data)/rate:.3f}s)")
        print(f"distinct values: {sorted(np.unique(data)[:12].tolist())}")

        if args.freq:
            print(f"\n{'bit':>4} {'main_run':>9} {'freq_hz':>10} {'duty':>7} {'runs':>6}")
            for bit in range(8):
                r = bit_freq(data, bit, rate)
                if r is None:
                    continue
                f, main, duty, nruns = r
                print(f"  b{bit} {main:9d} {f:10.0f} {duty*100:6.1f}% {nruns:6d}")

        with open(args.out, "wb") as fh:
            fh.write(data.tobytes())
        print(f"\nsaved {args.out}")
        return 0
    finally:
        try:
            dev.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
