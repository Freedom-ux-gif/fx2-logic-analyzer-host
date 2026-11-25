"""Verify our own WinUSB layer talks to the real device, replicating what Logic.exe does.

Logic.exe observed sequence (captured via frida spawn hooks, spawn_log.jsonl):
    WinUsb_SetPipePolicy(pipe=1,   policy=3 /*PIPE_TRANSFER_TIMEOUT*/)
    WinUsb_SetPipePolicy(pipe=129, policy=3)
    WinUsb_SetPipePolicy(pipe=1,   policy=8 /*RAW_IO*/)
    WinUsb_SetPipePolicy(pipe=1,   policy=4 /*IGNORE_SHORT_PACKETS*/)
    WinUsb_WritePipe(pipe=1,  data=61 d4)                      -> 2 bytes
    WinUsb_ReadPipe (pipe=129, len=1)                          -> 0x40
    WinUsb_WritePipe(pipe=1,  data=df c6 b3 51 60)             -> 5 bytes
    WinUsb_ReadPipe (pipe=129, len=8)                          -> 61 6f 91 d7 e4 49 46 ae

This script replays that sequence with our own ctypes layer. It must NOT run at
the same time as Logic.exe -- only one process can own the WinUSB handle.

Usage:
    python -I replay.py [--rate-byte d4] [--dry-run]
"""
import argparse
import os
import sys

# Running with -I drops the script's own directory from sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import winusb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate-byte", default="d4",
                    help="samplerate divider byte in hex (d4=8MHz per sigrok table)")
    ap.add_argument("--dry-run", action="store_true", help="only enumerate, do not open")
    args = ap.parse_args()

    devs = winusb.enumerate_devices()
    print("发现 %d 个设备" % len(devs))
    for d in devs:
        print("  %s  VID=%04x PID=%04x  %s" % (d["path"], d["vid"], d["pid"], d["model"]))
    if not devs:
        print("没有设备，退出")
        return 2
    if args.dry_run:
        return 0

    dev = winusb.SaleaeDevice(devs[0]["path"])
    try:
        dev.open()
        print("已打开设备，speed=%s" % (dev.query_speed(),))

        # Same policy sequence Logic.exe applies before the first transfer.
        for pipe, policy, name in [
            (1, winusb.PIPE_TRANSFER_TIMEOUT, "PIPE_TRANSFER_TIMEOUT"),
            (129, winusb.PIPE_TRANSFER_TIMEOUT, "PIPE_TRANSFER_TIMEOUT"),
            (1, winusb.RAW_IO, "RAW_IO"),
            (1, winusb.IGNORE_SHORT_PACKETS, "IGNORE_SHORT_PACKETS"),
        ]:
            val = 1000 if policy == winusb.PIPE_TRANSFER_TIMEOUT else 1
            try:
                dev.set_pipe_policy(pipe, policy, val)
                print("  SetPipePolicy(pipe=%d, %s, %d)  OK" % (pipe, name, val))
            except Exception as e:
                print("  SetPipePolicy(pipe=%d, %s)  FAILED: %s" % (pipe, name, e))

        rate = bytes.fromhex(args.rate_byte.ljust(2, "0"))
        print("\n--- 复现 Logic 的握手 ---")

        cmd1 = b"\x61" + rate
        n = dev.write_pipe(1, cmd1)
        print("  WritePipe(1, %s) -> %d bytes" % (cmd1.hex(), n))
        try:
            resp = dev.read_pipe(129, 1, timeout_ms=1000)
            print("  ReadPipe(129, 1) -> %s" % resp.hex())
        except Exception as e:
            print("  ReadPipe(129, 1) 超时/失败: %s" % e)

        cmd2 = bytes.fromhex("dfc6b35160")
        n = dev.write_pipe(1, cmd2)
        print("  WritePipe(1, %s) -> %d bytes" % (cmd2.hex(), n))
        try:
            resp = dev.read_pipe(129, 8, timeout_ms=1000)
            print("  ReadPipe(129, 8) -> %s" % resp.hex())
        except Exception as e:
            print("  ReadPipe(129, 8) 超时/失败: %s" % e)

        print("\n--- 尝试读取采样数据 ---")
        try:
            data = dev.read_pipe(129, 4096, timeout_ms=2000)
            print("  ReadPipe(129, 4096) -> %d bytes: %s" % (len(data), data[:64].hex()))
        except Exception as e:
            print("  ReadPipe(129, 4096) 失败: %s" % e)
    finally:
        dev.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
