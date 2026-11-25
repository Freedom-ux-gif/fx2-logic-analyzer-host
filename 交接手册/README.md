# 交接手册

> 项目：某宝克隆版 Saleae Logic 逻辑分析仪（`0925:3881`）逆向 + 自研上位机
> 硬件：Cypress FX2，8 通道纯数字，USB High Speed，最高 24 MHz
> 状态：**可用**。采集满速、波形显示、协议解码、时间轴、导出全部验证通过
> 更新：2026-11-25

---

## 从哪开始读

| 你是 | 先读 | 再读 |
|---|---|---|
| **只想用起来** | [H2 软件使用](H2_软件使用.md) 第 1 章 | H5 故障排查（出问题时） |
| **要改代码** | [H4 开发指南](H4_开发指南.md) 第 0~2 章 | H4 第 3 章的三个配方 |
| **要理解硬件协议** | [H1 硬件与协议](H1_硬件与协议.md) 第 3 章 | H5 错误码速查 |
| **要继续逆向** | [H3 逆向方法](H3_逆向方法.md) 第 1 章的方论 | H3 第 4 章证伪清单 |
| **要决定下一步做什么** | [H6 调研结论与路线](H6_调研结论与路线.md) 第 2 章 | 14_research/ 的 10 份原始调研 |
| **刚接手，什么都想知道** | 本篇往下读完 | 再按上表选 |

---

## 三十秒总览

### 这是什么

一个 20~30 块钱的淘宝克隆逻辑分析仪，原厂软件（Saleae Logic 1.2.11）是 2016 年的老东西，
界面英文、不开放、装一次 100 多 MB。**我们逆向了它，并写了一个自己的上位机。**

### 现在能做到什么

```
采样率      200 kHz ~ 24 MHz（10 档，全部实测满速）
通道        8 路纯数字
波形显示    缩放/平移/光标/时间轴（ns~s 自动切换）
协议解码    UART / I2C / SPI / CAN
测量        频率/占空比/边沿数/脉宽
触发        软件触发（边沿/电平/脉宽/模式/串口起始位）
导出        CSV / VCD / 二进制
界面        中文，网页版，双击 exe 即用
```

### 三个关键事实（不知道会浪费很多时间）

**① 必须先跑一次官方 Logic.exe**

插上设备后，先启动一次 `D:\Program Files\Saleae Inc\Logic.exe`，等它识别到设备，然后关掉。
这一步会把设备的端点表从「6 个奇怪的端点」改成「标准的 4 个，含数据端点 0x82」。
**跳过这步，我们的代码读不到任何数据。**

**② 命令必须加密**

发给设备的命令是 `{0x01, 48000000/rate - 1}`，但这 2 个字节要经过一个有状态混淆器。
明文发出去设备**不报错但不出数据**，加密后才正常。算法见 [H1 第 3.3 节](H1_硬件与协议.md)。

**③ 通道映射是 CH0→bit0，不是 CH1→bit7**

sigrok 文档说 Probe1 对应最高位，**这块板子相反**。接 CH0 采到的数据只有 bit0 在变。
代码里全部按 `CHn → bitn` 实现，并有测试锁死。

---

## 目录地图

```
项目根目录\
│
├── 交接手册\                     ← 你在这里
│   ├── README.md                 本篇（总入口）
│   ├── H1_硬件与协议.md          设备识别、USB 命令、混淆算法、端点、通道映射
│   ├── H2_软件使用.md            双击哪个、怎么操作、文件在哪、FAQ
│   ├── H3_逆向方法.md            加密 PE 怎么处理、方法论、证伪清单
│   ├── H4_开发指南.md            目录职责、代码地图、加解码器/改UI/加API 配方
│   ├── H5_故障排查.md            17 条症状排查树 + 错误码速查
│   └── H6_调研结论与路线.md      业界对比、优先级、不做什么
│
├── 13_web\                       ★★ 主产品：网页版上位机
│   ├── start.bat                 源码方式启动
│   ├── server.py                 后端（734 行，HTTP + 10 个 API）
│   ├── launcher.py               启动器（自检 → 起服务 → 开浏览器）
│   └── static\
│       ├── index.html            界面骨架
│       ├── style.css             深色/浅色主题
│       ├── app.js                前端全部逻辑（1152 行）
│       └── mock_server.py        前端独立测试用的假后端
│
├── 08_fx2\                       ★ 采集实现（唯一验证可用）
│   ├── capture_verified.py       加密命令 + 多线程读 + 采集
│   └── capture_fx2.py            早期版本（端点表不同，仅参考）
│
├── 03_host\                      ★ USB 底层
│   └── winusb.py                 纯 ctypes 的 WinUSB 封装，零第三方依赖
│
├── 09_app\                       ★ 解码与导出
│   ├── decoder_base.py           SampleStream / DecodeEvent / Decoder 基类
│   ├── decoder_uart.py           UART
│   ├── decoder_i2c.py            I2C
│   ├── decoder_spi.py            SPI
│   ├── decoder_can.py            CAN（含位填充、CRC-15）
│   ├── exporter.py               CSV / VCD / 二进制
│   ├── wave_view.py              降采样（供画布用）
│   └── synth.py                  合成测试数据生成器
│
├── 12_trigger\                   ★ 软件触发
│   ├── trigger.py                5 种触发器
│   └── triggered_capture.py      预触发采集
│
├── 14_research\                  10 份业界调研（2902 行）+ 路线图
│
├── 逆向方法论\                    ★ 逆向过程的分析结论（本发布版新增）
├── 已证伪路线\                    ★ 走不通的路及原因（本发布版新增）
│
├── 01_sdk\                       Analyzer SDK 的 ABI 索引（272 导出）
│
└── 历史目录（**其中 6 个未随本仓库分发**，见下方说明）
    ├── 00_notes\                 公开资料调研
    ├── 02_usb\                   frida USB 抓包          ← 未分发
    ├── 04_protocol\              协议探测记录            ← 未分发
    ├── 05_socket\                Socket API 探测（已证伪）← 未分发
    ├── 06_disasm\                反汇编分析              ← 未分发
    ├── 07_trigger\               触发实验                ← 未分发
    ├── tools\                    逆向工具链              ← 未分发
    ├── 10_gui\                   tkinter 完整版（备选界面）
    └── 11_pack\                  旧 tkinter exe（备用）
```

**★ = 核心，改之前先读懂。其余是历史记录或参考资料。**

> **关于「未分发」的六个目录**
>
> `02_usb/`、`04_protocol/`、`05_socket/`、`06_disasm/`、`07_trigger/`、`tools/` 属于原作者本地工程的一部分，**不在本公开发布版中**。原因有两类：
> - `06_disasm/`、`tools/` 含原厂程序的衍生物（内存镜像 `Logic_dumped.exe` 25 MB、逐字反汇编），不适合随仓库分发；
> - `02_usb/`、`04_protocol/`、`07_trigger/` 主要是体积巨大的 frida 抓包日志（合计约 14 MB），阅读价值低。
>
> **它们的结论已经整理进 [`已证伪路线/`](../已证伪路线/00_总览.md) 与 [`逆向方法论/`](../逆向方法论/00_总览.md)** —— 想了解「试过什么、为什么不行」，读这两个目录即可，不需要原始日志。
>
> 正文中若出现「见 `04_protocol/commands.md`」「见 `tools/dump_rpm.py`」这类路径，指的是原作者工程内部文件，本仓库不包含它们。相关方法论已改写进 `逆向方法论/03_工具说明.md`。

---

## 五分钟验货

按顺序跑这四条，全过就说明环境正常。

### 1. 设备在不在

```bash
powershell -NoProfile -Command "Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -match '0925'} | Format-Table Status,FriendlyName,InstanceId -AutoSize"
```

预期：`Status=OK`，`Saleae Logic USB Logic Analyzer`，`VID_0925&PID_3881`。

### 2. 端点对不对

```bash
cd 03_host
python -I -c "import sys;sys.path.insert(0,'.');import winusb;d=winusb.SaleaeDevice(winusb.enumerate_devices()[0]['path']);d.open();print('alt=',d.alt_setting);print([hex(p) for p,t,m,i in d.list_pipes()])"
```

预期：`alt= 0`，端点含 **`0x82`**。
如果是 `alt= 1` 且没有 `0x82` → **去跑一次 Logic.exe**。

### 3. 能不能采集

```bash
cd 08_fx2
python -I capture_verified.py --rate 1000000 --seconds 0.5 --freq --out /tmp/check.bin
```

预期：`captured` 后面是 50 万附近的数字（**不一定是精确 500000**——底层 `capture_timed` 会多读到一点上轮残留，`--seconds 0.5` 实际可能拿到 50~52 万），文件存到 `/tmp/check.bin`。

> 注：后端 `server.py` 会按 `rate × seconds` 精确裁剪，所以 Web 界面看到的样本数总是精确的；
> 直接用命令行 `capture_verified.py` 才会看到这个偏差。

### 4. 界面能不能开

双击 `13_web\dist_app\LogicWeb.exe` → 浏览器自动打开 → 徽章绿色「设备就绪」。

---

## 全部测试（71 个用例）

```bash
cd 项目根目录

cd 09_app    && python -I test_decoders.py      # 12
cd ../09_app && python -I test_view_export.py   # 8
cd ../09_app && python -I test_decoder_can.py   # 15
cd ../10_gui && python -I test_gui.py           # 10
cd ../12_trigger && python -I test_trigger.py   # 10
cd ../11_pack && python -I test_core.py         # 6
cd ../13_web && python -I test_server.py        # 10
```

**注意**：所有脚本必须用 `python -I` 跑（隔离模式，防目录劫持），所以脚本内都有 `sys.path.insert`。
如果自己写新脚本，记得照做。

---

## 关键数据速查

### 采样率与 delay 值

| 采样率 | delay | 明文命令 | 加密后 |
|---|---|---|---|
| 24 MHz | 1 | `01 01` | `d5 d5` |
| 16 MHz | 2 | `01 02` | `d5 d5` |
| 12 MHz | 3 | `01 03` | `d5 e2` |
| 8 MHz | 5 | `01 05` | `d5 d4` |
| 4 MHz | 11 | `01 0b` | `d5 da` |
| 2 MHz | 24 | `01 18` | `d5 e6` |
| 1 MHz | 47 | `01 2f` | `d5 8e` |
| 500 kHz | 95 | `01 5f` | `d5 fe` |
| 250 kHz | 191 | `01 bf` | `d5 9e` |
| 200 kHz | 239 | `01 ef` | `d5 4e` |

公式：`delay = 48000000 / rate - 1`

### 端点

| 端点 | 方向 | 用途 |
|---|---|---|
| `0x01` | OUT | 发命令 |
| `0x81` | IN | 命令应答（只回 1 字节） |
| `0x82` | IN | **采样数据** |
| `0x06` | OUT | 未使用（Logic16 代才用） |

### 数据格式

每个字节 = 8 个通道在同一时刻的电平，**CHn 对应 bitn**：

```python
ch0 = (byte >> 0) & 1
ch7 = (byte >> 7) & 1
```

### 性能实测

| 采样率 | 单线程 | 3 线程 + 64KB |
|---|---|---|
| 4 MHz | 25~100% | **100%** |
| 8 MHz | 0.5% | **100%** |
| 12 MHz | 0.4% | **100%** |
| 24 MHz | — | **100%**（24 MB/s） |

**单线程在 8 MHz 以上基本不可用**，必须多线程。

---

## 明确做不到的（别再试）

| 项 | 为什么 |
|---|---|
| **硬件触发** | 设备的触发寄存器协议没逆出来；libsigrok 的触发也是软件实现的（`soft-trigger.c`） |
| **模拟通道** | 这块板没有 ADC，纯数字 8 通道 |
| **超过 8 通道** | 硬件规格 |
| **超过 24 MHz** | FX2 High Speed 带宽上限 |
| **官方 Socket API** | 端口 10429，实测只收不回（702 个事件，服务端 0 字节发出） |
| **汉化官方软件** | UI 字符串编译进代码且磁盘加密，改不了 |

---

## 数据存在哪

```
C:\Users\<你的用户名>\Documents\LogicCapture\
    capture_20261125_143022_24MHz.bin
    capture_20261125_143022_24MHz.csv
    ...
```

- `.bin` 是裸字节，`每字节 = 8 通道`，需要配合采样率才能解析
- 文件名带采样率，方便回忆
- **当前已有 63 个文件**

界面上点状态栏的【打开文件夹】能直接打开。

---

## 继续往下做的建议

按 [H6 第 2 章](H6_调研结论与路线.md) 的优先级：

| 优先级 | 功能 | 工作量 |
|---|---|---|
| P0 | AB 区间标记 + 区间统计（脉冲数/占空比/时间） | 5 小时 |
| P1 | 加 5 个解码器（1-Wire/PWM/I2S/Manchester/DMX512） | 每个 2~3 小时 |
| P1 | 解码器参数自声明（加协议只写一个文件，不改 UI） | 4 小时 |
| P2 | 光标吸附到边沿、鼠标悬停实时测量 | 3 小时 |
| P3 | 会话保存/加载、采集历史 | 6 小时 |

**P0 的设计已经写好了**（`14_research/R7_timeline_ab_design.md`，566 行，含伪代码），照着实现即可。

---

## 法律与伦理

- 设备是**克隆版**，不是 Saleae 原厂产品，原厂 EULA 的约束力大幅削弱
- 参考实现 `keesj/saleae-logic-libusb` 是 **BSD-3-Clause**，`sigrok/libsigrok` 是 GPL（仅作协议参照，未复制代码）
- **建议**：不要商业分发基于逆向结果的成品，不要宣称兼容 Saleae 品牌
- 本次逆向目的是**互操作性**（让自家设备能在自己写的软件里用），不涉及破解授权或绕过付费

---

## 版本历史

| 日期 | 里程碑 |
|---|---|
| 2026-11-24 | 逆向启动：确认 Logic.exe 加密、RPM dump 突破、混淆器还原、SDK ABI 索引 |
| 2026-11-24 | 真机采集打通（8 kHz 方波验证） |
| 2026-11-25 | 24 MHz 满速（3 读线程）、网页版上位机、exe 打包 |
| 2026-11-25 | 时间轴（ns/µs/ms/s 自动切换）、10 路业界调研（2902 行） |
| 2026-11-25 | 交接手册（本篇 + H1~H6） |
