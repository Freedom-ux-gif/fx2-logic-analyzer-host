#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从本机 Saleae.inf 中实读设备接口 GUID（步骤 1）。

背景：Saleae 的 INF 为每个型号注册一个 DeviceInterfaceGUIDs 注册表项，
WinUSB 设备就是靠这些 GUID 被 SetupDiGetClassDevsW 枚举出来的。
本模块不猜 GUID、不查网络，只认本机磁盘上的 INF 文件。

注意：大脑实测声称该 INF 是 UTF-16LE，但本次实读发现前两字节是 b'[V'、
零字节占比为 0，实际是 ASCII。下面的检测算法两种情况都能正确处理
（严格遵循契约步骤 1.1），所以结论不受影响。
"""
import os
import re
import sys

# Windows 控制台默认 GBK，打印中文说明时可能炸；按大脑实测的踩坑经验统一重配。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# INF 的实路径；只读，不修改 Saleae 安装目录下的任何文件。
INF_PATH = r"D:\Program Files\Saleae Inc\Drivers\Saleae.inf"

# 匹配 INF 里的 AddReg 行：HKR,,DeviceInterfaceGUID(s),...,"{GUID}"
# 大小写不敏感，兼容 DeviceInterfaceGUID 与 DeviceInterfaceGUIDs 两种写法。
_GUID_LINE_RE = re.compile(
    r"DeviceInterfaceGUIDs?\s*,.*?\{\s*([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\s*\}",
    re.IGNORECASE,
)
_GUID_FULL_RE = re.compile(
    r"\{\s*[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\s*\}"
)
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def read_inf_lines(path=INF_PATH):
    """按契约步骤 1.1 的策略解码 INF，返回逐行文本（保留行号供报告引用）。"""
    with open(path, "rb") as f:
        raw = f.read()
    # BOM 或高零字节占比 => UTF-16LE；否则按 latin1 无损解码。
    if raw[:2] == b"\xff\xfe" or (len(raw) > 0 and raw.count(0) / len(raw) > 0.3):
        text = raw.decode("utf-16-le")
    else:
        text = raw.decode("latin1")
    return text.splitlines()


def parse_inf_guids(path=INF_PATH):
    """
    返回 (entries, guid_list)：
      entries: [(行号, 所在节名, 原文行, GUID), ...]
      guid_list: 去重后的 GUID 字符串列表（保留首次出现顺序）
    """
    entries = []
    guids = []
    section = ""
    for lineno, line in enumerate(read_inf_lines(path), 1):
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            continue
        m = _GUID_LINE_RE.search(line)
        if m:
            guid = _GUID_FULL_RE.search(line).group(0)
            entries.append((lineno, section, line.strip(), guid))
            if guid not in guids:
                guids.append(guid)
    return entries, guids


# 模块级常量：给 winusb.py / probe.py 直接 import 使用。
# 取 INF 中第一批设备（LogicInstall.HW -> Dev_AddRegLogic，第 162 行）的 GUID
# 作为默认 GUID；全部 7 个型号由 ALL_GUIDS 保留，见下方注释。
ENTRIES, ALL_GUIDS = parse_inf_guids()
GUID = ALL_GUIDS[0] if ALL_GUIDS else ""
GUID_SOURCE = "D:\\Program Files\\Saleae Inc\\Drivers\\Saleae.inf"

# 每个 GUID 对应的设备节 / 型号（均来自本机 INF 实读，非网络抄录）：
#   第 162 行 {21459242-8155-11DD-BC59-51D755D89593} <- [Dev_AddRegLogic]     （Logic，VID_0925&PID_3881）
#   第 165 行 {D509886E-3AA5-11DF-861E-86B356D89593} <- [Dev_AddRegLogic16]   （Logic16，VID_21A9&PID_1001）
#   第 168 行 {F8BF574A-E31C-40B6-8332-AD51EF1D325D} <- [Dev_AddRegLogicStart]（LogicStart，VID_21A9&PID_1002）
#   第 171 行 {DE7E53F9-378A-4DC9-9AE8-2D7619404112} <- [Dev_AddRegLogic4]    （Logic4，VID_21A9&PID_1003）
#   第 174 行 {03C61D2D-8A38-4FD3-9E60-1BCAA5FA28C1} <- [Dev_AddRegLogic8]    （Logic8，VID_21A9&PID_1004）
#   第 177 行 {DDB1D63F-0ECF-4E86-94E7-ADB4C765E352} <- [Dev_AddRegLogicPro8] （LogicPro8，VID_21A9&PID_1005）
#   第 180 行 {DDB1D63F-0ECF-4E86-94E7-ADB4C765E353} <- [Dev_AddRegLogicPro16]（LogicPro16，VID_21A9&PID_1006）


def main():
    if not ENTRIES:
        print("错误：未能从 INF 解析出任何 DeviceInterfaceGUID：", INF_PATH)
        return 1
    print("INF 文件：", INF_PATH)
    print("找到以下 DeviceInterfaceGUIDs 注册表项原文：")
    for lineno, section, raw_line, guid in ENTRIES:
        print(f"  第 {lineno} 行 [{section}]: {raw_line}")
    print("\n去重后的 GUID（共 %d 个）：" % len(ALL_GUIDS))
    for g in ALL_GUIDS:
        print("  ", g)
    print("\n模块常量 GUID =", GUID, "（对应 Dev_AddRegLogic / LogicInstall.HW，INF 第 162 行）")
    print("INF 实读字节序：", "UTF-16LE" if open(INF_PATH, "rb").read(2) == b"\xff\xfe" else "ASCII/latin1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
