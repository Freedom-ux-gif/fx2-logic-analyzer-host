# Saleae 逻辑分析仪 — 公开资料调研

## 0. 方法与免责（本报告只收公开来源，未验证项明确标注）

- 本报告只收录本次实际 fetch 成功（HTTP 200）的公开页面；每条外部结论后紧跟 `[来源: <URL>]`。没有可访问 URL 的内容一律写「无公开资料」或标 `[推断，未验证]`。
- 本报告用于给后续运行时抓包对账当**参照系**，不是当真相：sigrok 的文档描述的是「换用开源固件 fx2lafw 后」的协议，而本项目目标是原厂 Logic 1.2.11 固件 + WinUSB，两者协议可能不同。[推断，未验证]
- 摘句每处 ≤2 行；中文撰写，代码/协议字段名保留原文。
- 本机基线（VID/PID、驱动、软件版本）为大脑与本人实读，标 `[本机实读]`，不视为外部来源。

## 1. 设备与驱动基线（VID/PID 表 + 驱动模型，来源：本机 INF 实读）

- 目标软件 Saleae Logic 1.2.11（2016-12-07），x64，`.text` 熵 8.00，已混淆，静态反汇编无效，只能靠运行时抓包。[本机实读]
- 驱动模型：WinUSB。[本机实读]
- 插件 ABI：`CreateAnalyzer` / `DestroyAnalyzer` / `GetAnalyzerName` 三个 C 入口。[本机实读]

| VID:PID | 型号 | 属性 |
|---|---|---|
| 0925:3881 | Saleae Logic（FX2 代，8 通道） | USB 描述符 `ID 0925:3881 Lakeview Research` 可由 sigrok 的 lsusb 记录交叉印证 [来源: https://sigrok.org/wiki/Saleae_Logic/Info]；本机 INF 实读 [本机实读] |
| 21A9:1001 | Logic16 | `Bus 001 Device 039: ID 21a9:1001` 见 sigrok 的 lsusb 记录 [来源: https://sigrok.org/wiki/Saleae_Logic16/Info]；本机 INF 实读 [本机实读] |
| 21A9:1002 | LogicStart | 本机 INF 实读 [本机实读] |
| 21A9:1003 | Logic4 | 本机 INF 实读 [本机实读] |
| 21A9:1004 | Logic8 | 本机 INF 实读 [本机实读] |
| 21A9:1005 | LogicPro8 | 本机 INF 实读 [本机实读] |
| 21A9:1006 | LogicPro16 | 本机 INF 实读 [本机实读] |

## 2. sigrok / libsigrok 支持现状（逐型号表格：型号 / PID / 是否有驱动 / 来源 URL）

- libsigrok 是 sigrok 的硬件后端库；GitHub 仓库 `sigrokproject/libsigrok` 是官方 `git://sigrok.org/libsigrok` 的只读镜像。[来源: https://github.com/sigrokproject/libsigrok]
- `src/hardware/` 下与 Saleae 相关的驱动目录为 `fx2lafw`、`saleae-logic16`、`saleae-logic-pro`；**没有** `saleae-logic` 目录（这正是大脑试过的 404 路径）。[来源: https://api.github.com/repos/sigrokproject/libsigrok/contents/src/hardware]
- sigrok 的「Supported hardware」页列出 Saleae Logic 与 Saleae Logic16 两个条目。[来源: https://sigrok.org/wiki/Supported_hardware]

| 型号 | PID | sigrok 驱动 / 目录 | 支持状态 | 来源 URL |
|---|---|---|---|---|
| Saleae Logic（FX2 代，8 通道） | 0925:3881 | `fx2lafw`（换用开源固件） | 「In sigrok, we use the open-source fx2lafw firmware for this logic analyzer.」 | https://sigrok.org/wiki/Saleae_Logic ; https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/fx2lafw |
| Logic16 | 21A9:1001 | `saleae-logic16`（`api.c`/`protocol.c`/`protocol.h`） | 页面标为 supported；「the USB driver must also be installed using Zadig」 | https://sigrok.org/wiki/Saleae_Logic16 ; https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic16 |
| LogicPro8 / LogicPro16 | 1005 / 1006 | `saleae-logic-pro`（`api.c`/`protocol.c`/`protocol.h`） | 有独立驱动目录，支持程度页面未说明 | https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic-pro ; https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/saleae-logic-pro/api.c |
| LogicStart / Logic4 / Logic8 | 1002 / 1003 / 1004 | 未找到专门驱动 | 无公开资料（在 `src/hardware/` 中未见对应目录） | https://api.github.com/repos/sigrokproject/libsigrok/contents/src/hardware |

## 3. fx2lafw 协议要点（原文摘句 + URL，只摘与「控制命令、采样率配置、数据管道」相关的）

- 固件定位：「fx2lafw is an open-source firmware for Cypress FX2 chips which makes them usable as simple logic analyzer and/or oscilloscope hardware.」[来源: https://sigrok.org/wiki/Fx2lafw]
- 适用面：「The fx2lafw firmware is meant to work on any FX2-based hardware, including logic analyzers, FX2 eval boards, oscilloscopes, or other hardware which has this chip on-board.」[来源: https://sigrok.org/wiki/Fx2lafw]
- 采样时钟：「All devices use a 24MHz crystal. For 8 probes the FX2 pins PB0-PB7 are used, for 16 probes PB0-PB7 and PD0-PD7.」[来源: https://sigrok.org/wiki/Fx2lafw]
- sigrok 明确说明换固件后不需要原厂协议，但留有旧版厂商协议文档：「Since we use the open-source fx2lafw firmware for this device, we don't need to know the protocol.」「However, for those interested in this, see our old vendor protocol docs」[来源: https://sigrok.org/wiki/Saleae_Logic]
- **原厂（厂商）协议要点**（sigrok 的旧文档，正是本项目最需要的参照）：「There is only one command the software sends to the Saleae Logic on endpoint 1」「a two-byte command to set the samplerate」[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- 命令字节：「The first byte is always 0x01 (0xd5 on more recent firmware versions).」「The second byte indicates the samplerate.」[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- 采样率公式：「samplerate = 48 / (1 + divider)」。[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- 数据管道：「endpoint 1 (out) is used for sending commands to the logic analyzer」「endpoint 2 (in) is for transfers of sample sets」「Both endpoints are of type bulk.」[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- 样本编码：「Samples are read off endpoint 2.」「A sample is one byte, with each bit representing the state of one of the probes.」[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- USB 描述符交叉印证：`bEndpointAddress 0x01 EP 1 OUT` / `0x81 EP 1 IN` / `0x02 EP 2 OUT`，`Transfer Type Bulk`，`wMaxPacketSize 0x0200 1x 512 bytes`。[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
- 开源固件 `fx2lafw/protocol.c` 里的控制请求（与上面的原厂协议不同，是**开源固件的 CMD_\***）：vendor IN `CMD_GET_FW_VERSION`（2 字节响应）、vendor IN `CMD_GET_REVID_VERSION`（1 字节响应）、vendor OUT `CMD_START`，其 payload 为 `flags` + `sample_delay_h` + `sample_delay_l`。[来源: https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/fx2lafw/protocol.c]
- 该 `CMD_START` 的 flags 位选择 48MHz 或 30MHz 时钟、8-bit 或 16-bit 采样，以及模拟通道启用时的 CTL2 时钟；批量数据用端点 `2 | LIBUSB_ENDPOINT_IN`（IN 方向 EP2），控制超时常量 100。[来源: https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/fx2lafw/protocol.c]

## 4. Logic16/Pro 系列与 FX2 代的差异（有资料才写，没有就写「无公开资料」）

- Logic16 由独立的 `saleae-logic16` 驱动处理，不是 `fx2lafw`。[来源: https://sigrok.org/wiki/Saleae_Logic16]
- Logic16 的配置 Endpoint：「Endpoint 1 is used for configuration of the analyzer.」[来源: https://sigrok.org/wiki/Saleae_Logic16]
- Logic16 的数据「加密」：「The transfers are "encrypted" using a simple series of additions and XORs.」[来源: https://sigrok.org/wiki/Saleae_Logic16]
- Logic16 样本组织：「The samples (as received via USB) for the enabled probes (3, 6, 9, or 16) are organized as follows」[来源: https://sigrok.org/wiki/Saleae_Logic16]
- Logic16 VID/PID：`idVendor 0x21a9` / `idProduct 0x1001`，且这时设备枚举出 `bNumEndpoints 6`，含 `0x01 EP 1 OUT`、`0x86 EP 6 IN`、`0x88 EP 8 IN` 等——与 FX2 代的 2 端点通信模型显著不同。[来源: https://sigrok.org/wiki/Saleae_Logic16/Info]
- LogicPro8/16 有独立 `saleae-logic-pro` 驱动目录，但其具体协议差异：无公开资料（本次只在仓库里确认目录与源码文件存在）。[来源: https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic-pro]
- LogicStart / Logic4 / Logic8（1002/1003/1004）的协议差异：无公开资料。[本机实读 + 无公开资料]

## 5. .logicdata 文件格式（有无公开文档 / 有无开源解析器 / 各自结论）

- 在本次检索范围内，未找到 sigrok 官方或其他来源公开的 `.logicdata` 二进制格式规范页；sigrok wiki 的 `Logicdata` / `File_format:Logicdata` 路径均返回 404（见「已尝试但失效的路径」）。
- GitHub 搜索 `saleae logicdata`、`saleae logicdata parser`、`logicdata file format`、`saleae logicdata reverse engineering` 均未返回解析 `.logicdata` 捕获文件的仓库；命中的 `logicdata` 多为办公升降桌同名产品（如 `smartalock/LogicDataAnalyzer`），与 Saleae 无关。[来源: https://api.github.com/search/repositories?q=saleae+logicdata&sort=updated&per_page=10]
- 找到的唯一相关第三方工具是 CSV 后处理工具，不是 `.logicdata` 解析器：`ibrahim-isikli/salea-logic-2-parser-to-bin`，描述「Python GUI tool for converting Saleae Logic2 parsed .csv files to ImHex-compatible .bin.」，即输入是 Logic 2 已导出的 CSV，而非原始 `.logicdata`。[来源: https://github.com/ibrahim-isikli/salea-logic-2-parser-to-bin]
- 结论：`.logicdata` 文件格式**无公开逆向文档、无已验证开源解析器**；本项目若需读取旧版捕获文件，只能自己做二进制逆向。[推断，未验证]

## 6. 第三方替代客户端（表格：项目 / 语言 / 支持型号 / 最后更新时间 / URL）

- sigrok 项目提供命令行前端：`sigrok-cli (sometimes abbreviated as "cli") is a command-line frontend for sigrok.`；「Use the -L (--list-supported) option to get a list of available drivers.」[来源: https://sigrok.org/wiki/Sigrok-cli]
- sigrok-cli 的支持矩阵由所装驱动决定（见第 2 节），不是单一型号客户端。[来源: https://sigrok.org/wiki/Supported_hardware]

| 项目 | 语言 | 支持型号 | 最后更新时间 | URL |
|---|---|---|---|---|
| libsigrok（fx2lafw 驱动） | C | Saleae Logic（0925:3881，换 fx2lafw 固件） | 仓库 2026-11-16 更新 | https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/fx2lafw |
| libsigrok（saleae-logic16 驱动） | C | Logic16（21A9:1001） | 仓库 2026-11-16 更新 | https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic16 |
| libsigrok（saleae-logic-pro 驱动） | C | LogicPro8/16（1005/1006） | 仓库 2026-11-16 更新 | https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic-pro |
| sigrok-cli | C（前端） | 取决于已装驱动；含 Saleae 专用 driver id | 页面未标注 | https://sigrok.org/wiki/Sigrok-cli |
| ibrahim-isikli/salea-logic-2-parser-to-bin | Python | 仅处理 Logic 2 导出的 CSV，非硬件客户端 | 2026-08-27 | https://github.com/ibrahim-isikli/salea-logic-2-parser-to-bin |

## 7. 对本项目的直接可复用结论（≤8 条，每条必须回指上面的 URL）

1. FX2 代原厂协议只有一条 EP1 OUT 控制命令，2 字节：第 1 字节 `0x01`（较新固件 `0xd5`），第 2 字节为分频值；采样率 = 48/(1+divider)。[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
2. FX2 代数据走 EP2 IN、bulk 传输，每字节代表一个探针的状态位。[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
3. `0925:3881` 枚举出 6 个端点（EP1/2/4 OUT + EP1/6/8 IN），但原厂协议实际只用 EP1 OUT 与 EP2 IN；抓包时重点核对这两条。[来源: https://sigrok.org/wiki/Saleae_Logic/Info]
4. Logic16 是另一套协议：EP1 配置，数据在其它端点，且样本做了加法+XOR 的简单混淆；抓包时须单独处理，不能套用 FX2 结论。[来源: https://sigrok.org/wiki/Saleae_Logic16]
5. Logic16 启用探针数为 3/6/9/16 时样本组织不同；这是解码逻辑16抓包数据的关键约束。[来源: https://sigrok.org/wiki/Saleae_Logic16]
6. 上述 sigrok 的「vendor protocol」是**旧版原厂协议文档**，与本项目 Logic 1.2.11 固件未必完全一致——它只作参照，不作真相。[来源: https://sigrok.org/wiki/Saleae_Logic] [推断，未验证]
7. sigrok 用 fx2lafw 开源固件替换原厂固件后才不需要原厂协议；本项目走 WinUSB 原厂路径，不能照搬 `fx2lafw/protocol.c` 的 `CMD_START`/`CMD_GET_FW_VERSION` 命令码。[来源: https://sigrok.org/wiki/Fx2lafw] [来源: https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/fx2lafw/protocol.c]
8. 读取旧版 `.logicdata` 捕获文件没有现成解析器可用，若抓包对账需要解析它，须自行逆向。[来源: https://github.com/ibrahim-isikli/salea-logic-2-parser-to-bin] [推断，未验证]

## 8. 待验证清单（抓包时要验证的问题，只写问题不写答案）

- Logic 1.2.11 实际下发的控制命令字节是否仍为 `0x01`/`0xd5` + 分频值？分频值与采样率的对应关系是否仍符合 48/(1+divider)？
- WinUSB 下控制传输是 vendor request 还是标准类请求？`bmRequestType`/`bRequest`/`wValue`/`wIndex` 的实际值是什么？
- 原厂固件下数据是否仍只走 EP2 IN？EP1 IN/EP4 OUT/EP6 IN/EP8 IN 在抓包中是否有活动、分别承担什么？
- `21A9:1001` Logic16 在 Logic 1.2.11 下的配置命令与端点使用是否和 sigrok 文档一致？加法+XOR 混淆的具体序列是什么？
- 样本 bit 顺序 / 字节序（哪个 bit 对应哪个探针）是否与原厂协议文档一致？
- `21A9:1002/1003/1004/1005/1006` 各型号的端点布局、配置命令与 FX2 代/Logic16 有何差异？
- Logic 1.2.11 是否在抓包前先上传 FX2 固件（如 fx2lafw 或原厂 hex）？枚举前后端点是否变化？
- 若需解析 `.logicdata`，其文件头/块结构为何？是否值得自用逆向而非从抓包重采？

## 已尝试但失效的路径（404 或无法访问，避免重复踩坑）

- `https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/saleae-logic/api.c` — **404**（大脑已实测，本人复测仍 404；仓库中不存在 `src/hardware/saleae-logic` 目录）。
- `https://github.com/sigrokproject/libsigrok/tree/master/src/hardware/saleae-logic` — **404**（该驱动目录不存在）。
- `https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/saleae-logic/protocol.c` — **404**（同上）。
- `https://sigrok.org/wiki/Logicdata` — **404**（无此页面）。
- `https://sigrok.org/wiki/File_format:Logicdata` — **404**（无此页面）。
- `https://sigrok.org/wiki/Software` — **404**。
- `https://sigrok.org/wiki/Sigrok_CLI` — **404**（正确路径是 `Sigrok-cli`）。
- `https://github.com/sigrokproject/libsigrok/issues/1194` — **404**（猜测的 issue 号，不存在）。
- `https://github.com/0x4D31/saleae-logicdata` / `https://github.com/gadgetoid/saleae-logic` / `https://github.com/saleae/logicdata` — **404**（猜测的 `.logicdata` 解析器仓库，均不存在）。
- `https://support.saleae.com/` — **302** 重定向到 `https://www.saleae.com/support`（后者 200，但为通用支持页，未给出旧设备协议/固件文档）；Saleae 官方旧设备 USB 协议：**无公开资料**。[来源: https://www.saleae.com/support]
- DuckDuckGo / Google 搜索页返回人机验证，未作为来源使用。

## 验收记录（步骤 4，实跑输出）

- 4.1 `ls -la`（`00_notes\`）：
```
total 48
drwxr-xr-x 1 TALE 197121     0 Nov 24 20:49 .
drwxr-xr-x 1 TALE 197121     0 Nov 24 20:40 ..
-rw-r--r-- 1 TALE 197121 16659 Nov 24 20:49 external_refs.md
-rw-r--r-- 1 TALE 197121 13384 Nov 24 20:49 rea_readiness.md
-rw-r--r-- 1 TALE 197121  5110 Nov 24 20:49 toolchain.md
```
- 4.2 `grep -o 'https\?://[^ )\]]*' external_refs.md | sort -u | wc -l` → **30**（要求 ≥6，通过）。
- 4.3 抽查 2 个关键 URL（`curl -s -m 10 -o /dev/null -w "%{http_code}"`）：
```
200  https://sigrok.org/wiki/Saleae_Logic/Info
200  https://raw.githubusercontent.com/sigrokproject/libsigrok/master/src/hardware/fx2lafw/protocol.c
```
两个均为 200，无 404，无需替换。
- 4.4 `grep -c "\[来源:" external_refs.md` → **38**（要求 ≥8，通过）。
- 4.5 `wc -l external_refs.md rea_readiness.md toolchain.md`：
```
  146 external_refs.md
  122 rea_readiness.md
   92 toolchain.md
  360 total
```
三个文件均 ≤300 行。[本机实读]
