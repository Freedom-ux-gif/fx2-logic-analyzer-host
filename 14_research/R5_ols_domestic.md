# OLS 与国产上位机调研

> 调研目的：我们已有 8 通道数字波形/缩放平移/光标/采集/软件触发/UART-I2C-SPI-CAN/频率占空比脉宽/CSV-VCD 导出，用户抱怨"功能太少"，要加时间线和 AB 区间测量。本文只调研**非西方主流**与老牌开源上位机的**交互/功能设计**，供借鉴，不深挖代码。
> 调研日期：2026-11-25。说明：契约里给的 `blackmesalabs/ols`、`asteroid-emu/OLS` 两个 GitHub 链接本日返回 404（已实测），sigrok wiki 的 OLS 页面同样 404；本文用 GitHub API 实际存在的仓库与可用网页替代，并逐条注明来源。

## 0. 资料来源

**A 类（OLS / 老牌开源）**
- [A1] `GadgetFactory/ols`（OpenBench LogicSniffer/SUMP 官方 Java 客户端源码，nl.lxtreme.ols）：https://github.com/GadgetFactory/ols ；实测 API 可读（604 个文件）。具体文件：`client/src/main/java/nl/lxtreme/ols/client/diagram/laf/DiagramTimeLineUI.java`、`client/.../action/SetCursorModeAction.java`、`SetCursorAction.java`、`tool.measure/.../MeasurementDialog.java`、`util/.../DisplayUtils.java`。
- [A2] `GadgetFactory/OpenBench-Logic-Sniffer`（super project，聚合 client/tools/固件）：https://github.com/GadgetFactory/OpenBench-Logic-Sniffer
- [A3] sigrok-cli 官方 manpage 源码（仓库 `sigrokproject/sigrok-cli`, `doc/sigrok-cli.1`）：https://github.com/sigrokproject/sigrok-cli/blob/master/doc/sigrok-cli.1 。sigrok.org 网页版本本次返回 404，故引用源码仓库原文。
- [A4] sigrok 官网 Downloads 页面（可访问，确认 sigrok-cli/PulseView 为官方组件）：https://sigrok.org/wiki/Downloads
- [A5] 中文 sigrok/PulseView 教程（博客园 Milton）：https://www.cnblogs.com/milton/p/15376584.html —— 内含中文界面术语与 Show Cursors 操作流程。
- [A6] Saleae Logic 1.x 的 UI 细节：**未找到公开资料**（搜索仅得 Logic 2 现代版页面和 SE 问答，无法核实老版测量面板）。不编造。

**B 类（国产上位机 / 中文教程）**
- [B1] KingstVIS 官网下载页（青岛金思特）：https://www.qdkingst.com/cn/download-vis —— 原文："KingstVIS软件可以采集记录多路数字信号，可测量信号脉宽、周期、频率、占空比等，可依据多种标准协议解析出通信数据，具备演示模式可让您在购买之前体验全部功能。"
- [B2] CSDN《KingstVIS逻辑分析仪使用教程》（2026-03）：https://blog.csdn.net/aiaida/article/details/158696119
- [B3] CSDN《KingstVIS逻辑分析仪使用指南》（2022-11）：https://blog.csdn.net/hs977986979/article/details/127686972
- [B4] 金思特《虚拟仪器使用手册》PDF（官网/云托管）：https://offer-product.oss-cn-beijing.aliyuncs.com/product/offer/attachment/null/file/subPdf_846323_371994_20240614-155523408.pdf
- [B5] 知乎《推荐最近在使用的还不错的一款逻辑分析仪》：https://zhuanlan.zhihu.com/p/690249863 （搜索摘要可见，强调采样率 5×/10× 规则；正文本次未抓到，谨慎引用）
- [B6] DSLogic 上位机界面细节：**未找到公开资料**（搜索结果多为 DSLogic 硬件/sigrok 兼容讨论，无可信的界面说明）。不编造。
- [B7] B 站/知乎视频类教程的具体操作演示：**未找到可抓取的文字资料**（B 站页面反爬）。不编造。

## 1. A 类：OLS / 老牌开源客户端

### 1.1 界面结构

OLS 客户端是 Java/Swing 桌面程序（包 `nl.lxtreme.ols`），由多个 Maven 模块装配（client / api / tool.* / device.*）。与界面直接相关的结构：

- `Diagram` 是核心波形画布组件（`client/diagram/Diagram.java`），置于 `JScrollPane` 中；图大小随采样点/缩放变化。[A1]
- `DiagramTimeLine` 是独立时间轴组件（`DiagramTimeLine.java`），与波形分离、共享滚动；自身实现 `DiagramCursorChangeListener`，光标变化会重画时间轴。[A1]
- `DiagramLabelsDialog` / `ModeSettingsDialog` / `GeneralSettingsDialog` 承担通道标签与显示模式配置，即"设置藏在对话框里，主界面保持干净"。[A1]
- 工具以插件/分析器形式组织：`tool.i2c`、`tool.uart`、`tool.spi`、`tool.jtag`、`tool.1wire`、`tool.state`、`tool.measure` 各有独立 Analyzer+Dialog+Worker。[A1]
- 菜单动作层有 `GotoCursor1Action`、`GotoCursor2Action`、`GotoFirstCursorAction`、`GotoLastCursorAction`、`GotoNextCursorAction`、`GotoPreviousCursorAction`、`GotoTriggerAction`、`ClearCursors`、`SetCursorModeAction`（助记键 C）等，说明**光标导航是独立的一级功能**。[A1]

### 1.2 测量工具设计

来自 `MeasurementDialog.java` 与 `DisplayUtils.java` 的实证：[A1]

- 测量对话框是**非模态（MODELESS）**窗口，用 `javax.swing.Timer(500ms)` 每半秒刷新一次所有读数——拖动波形或光标时数值持续更新，不用点"计算"。
- 对话框内有 `JComboBox cursorA / cursorB`，可从 `CapturedData.MAX_CURSORS` 个光标中任选两个作为 AB；A、B 的选择被持久化到 UserSettings（下次打开恢复）。
- 每个光标有一个 `cursorValueLabels[i]` 显示其绝对时间值；另有 `frequencyLabel`、`distanceLabel`、`clockFrequencyLabel`、`clockDutyCycleLabel` 四个读数标签。
- AB 计算：`diff = cursorApos - cursorBpos`，`distance = diff / sampleRate`（时间），`frequency = |sampleRate / diff|`（1/间距）。间距为零时显示 `<???>` 占位。
- 另有独立的 `ClockFrequencyMeasureWorker`：选一个通道，自动估算该通道的**时钟频率与占空比**（`stats.getFrequencyDisplayText()` / `getDutyCycleDisplayText()`），即"无需手动放光标"的自动测量。
- 时间格式化 `DisplayUtils.displayTime()`：按量级自动选 s / ms / μs / ns / ps，固定 3 位小数，数值与单位间一个空格（文档注释例子 "1.000 ms"）。频率格式化 `displayFrequency()`：Hz / kHz / MHz / GHz / THz，%.3f。
- 时间轴 `DiagramTimeLineUI`：`TIMELINE_INCREMENT=20px`、`TIMELINE_HEIGHT=30px`、`LONG_TICK_INTERVAL=10`、`TIME_INTERVAL=20`、`SHORT_TICK_HEIGHT=4px`。长刻度画标签、短刻度只画线；刻度间隔随缩放 `scale` 自适应（`tickInc = max(1, MAX_SCALE/scale)`）；触发点作为时间原点（`absoluteTime = time - triggerPosition`）；光标在时间轴上画"旗标"并显示该光标时间值 `DisplayUtils.displayTime()`。

### 1.3 可抄点

1. **时间轴与波形分离组件**：时间轴可独立滚动、独立点击/拖动光标，旗标上直接显示时间值——比把刻度画在波形画布上更清晰。
2. **非模态常驻测量面板 + 定时刷新**：拖动/缩放时数值跟着变，交互闭环短。
3. **AB 光标可任意选编号**：不是固定"光标 1/2"，任意两个光标都能组成区间；选择结果记忆。
4. **"自动测时钟"按钮**：对周期信号一键出频率/占空比，作为手动 AB 的补充。
5. **时间/频率单位自动缩放**：s/ms/μs/ns/ps 与 Hz~THz 的 3 位小数格式，可直接照搬显示规则。
6. **光标导航动作族**：跳到首/末/上一个/下一个光标、跳到触发点，密集波形里很有用。
7. **sigrok-cli 的 `-P/--protocol-decoders` 设计** [A3]：逗号分隔的解码器 ID 列表，每个 ID 后可接冒号分隔的 `key=value`（例 `uart:baudrate=115200:parity=odd`）；`-O/--output-format` 同样支持 `key=value`（例 `csv:dedup:header=false`、`hex:width=128`），布尔选项不写值即为 true。这套"**协议+参数串**"的表达方式可作为我们解码器配置的文本化/可复制方案，也利于脚本化与复现实验。
8. **中文 PulseView 教程** [A5] 用 "Show Cursors" 测时间跨度、"+/- 或竖滚轮缩放、横滚轮平移"，说明"滚轮分方向缩放/平移"是用户已有心智。

## 2. B 类：国产上位机（KingstVIS / DSLogic 等）

### 2.1 界面结构

以 KingstVIS 3.6.6（Windows/Mac/Linux，官网可下载，含全功能演示模式）为样本 [B1]。依据两篇 CSDN 教程 [B2][B3] 的界面描述：

- **顶部工具栏**：设备设置与主菜单入口（阈值电压、通道、采样深度、采样率、触发）。
- **左侧通道设置栏**：已启用通道编号/名称；通道两端有"上一个边沿/下一个边沿"居中按钮。
- **中部波形显示窗口**：时间轴 + 波形 + 解码结果叠加，底部滚动条。
- **右侧采样结果分析窗口**：测量面板、协议解析器设置、解码结果列表；解码输出可选 hex/十进制/二进制/ASCII，可单独导出。
- **缩放/平移交互** [B2][B3]：左键单击放大、右键单击缩小、滚轮上下缩放、**左键按住拖动左右平移**；点通道左侧按钮把前一个边沿移到中心、右侧按钮把后一个边沿移到中心。

DSLogic 上位机的独立界面资料：**未找到公开资料**（B6），不编造。

### 2.2 测量面板设计（重点）

KingstVIS 右侧"测量窗口"的实证（[B3] 原文）："①、脉宽：显示鼠标当前所在位置脉冲（简称当前脉冲）的宽度；②、周期：当前脉冲与下一个脉冲所组成的一个完整周期的周期值；③、占空比：当前脉冲与下一个脉冲组成的完整周期内高电平时间的占比；④、频率：上述②周期值的倒数。"

设计要点：

1. **测量以鼠标为中心**（"当前位置脉冲"），不像传统示波器必须放两个光标——这是它"好用"口碑的关键：鼠标指哪测哪，零操作成本。
2. 四项指标（脉宽/周期/占空比/频率）成组显示，且在测量面板的小设置控件里可勾选启用/禁用哪些项——**信息密度可控**。
3. 采样结果分析窗口把"测量 + 解码设置 + 解码结果"集中在右侧一栏，波形区不被属性面板挤占。
4. 官网 [B1] 对功能的官方表述与教程一致：脉宽、周期、频率、占空比 + 标准协议解析。
5. **KingstVIS 是否有独立的 AB 双光标区间测量面板：未找到公开资料**（教程只描述鼠标感应式测量与边沿居中，未提到命名游标）。不编造。
6. 《虚拟仪器使用手册》[B4] 存在且可下载，但本次未逐页核对其中光标/测量章节，故不据此声称更多细节。

### 2.3 可抄点

1. **鼠标悬停即测当前脉冲**：在波形上移动鼠标，右侧面板实时给出脉宽/周期/占空比/频率。这比"先放 A 再放 B 再读数"轻得多，适合作为我们 AB 测量之外的"快速模式"。
2. **边沿居中按钮**（上一边沿/下一边沿）：用于快速把关注跳变移到屏幕中央，再放大看细节——比单纯缩放平移更贴用户任务。
3. **测量项可勾选显示**：让用户按场景精简面板，避免信息过载。
4. **右侧集中分析栏**（测量+解码设置+结果同栏）：一屏完成"看波形→加解码→读数值"的闭环。
5. **演示模式**（未接硬件也能全功能体验）：降低试用门槛，可作为我们软件的教学/演示模式思路。[B1]
6. **采样率的经验法则写进教程**（5×信号频率、最低 10×；9600→50kHz、115200→1MHz）[B3]：我们可在采样设置处给出同样的提示/预设，减少用户踩坑。

## 3. 中文用户的真实使用习惯

（来自教程/论坛的高频操作，≥6 条，每条附来源）

1. **先接 GND 再接信号线，强调多点接地**：两篇 KingstVIS 教程都单列步骤并反复提醒"GND 直连、尽量不要共用一个接地点"——国产教程对接地异常执着，反映读者常踩这个坑。[B2][B3]
2. **采样率按 5×/10× 经验法则选**：教程列出 9600→50kHz、115200→1MHz 等速查值，并说明"采样时间=深度/采样率、分辨率=采样周期"。[B3]；知乎也有"5 倍以上、推荐 10 倍"的说法 [B5，仅搜索摘要]
3. **UART 用下降沿触发**：因空闲为高、起始位为低；教程明确建议下降沿。[B2][B3]
4. **左键放大/右键缩小/滚轮缩放/拖动平移**是被写进教程正文的基本功；教程还教"点通道两端按钮把前/后边沿移到中心"。[B2][B3]
5. **解码器是核心目的**：教程用大篇幅讲"添加 UART/I2C/SPI/modbus 解析器→配通道和参数→重新采集→看叠加结果与右下角数据"，支持 hex/十进制/二进制/ASCII 输出与单独导出。[B2][B3]
6. **测量以鼠标位置为准**：教程按"当前脉冲"定义脉宽/周期/占空比/频率，用户不需要先学光标操作就能读数。[B3]
7. **解码失败时的排查三板斧**：检查阈值电压、采样率是否太低、解码参数（波特率/反相/主从模式）是否设错。[B2][B3]
8. **中文 PulseView 教程教的是"Show Cursors"测时间跨度**：说明中文用户也接受"先开光标显示再测"的模式，但术语采用英文菜单+中文解释混排。[A5]
9. **采样深度/带宽的取舍被反复讨论**：中文社区常问"多少采样率够用"，教程主动给出对照表，说明用户关心可操作性而非理论。[B3][B5]

## 4. 术语对照

| 英文 | 中文常见译法 | 建议我们用什么 |
|---|---|---|
| cursor | 光标（主流）；游标（少见，多见于"游标卡尺"类比）；标记（偶尔） | 光标；首次出现标注"Cursor"，不混用"游标/标记" |
| time cursor / AB cursor | 时间光标 / AB 光标；游标 A/B | 用"A 光标 / B 光标"（与 CH 编号并列，一看就懂） |
| ruler / scale | 标尺 / 刻度（时间轴刻度） | 刻度（时间轴）；"标尺"容易与测量尺混淆，慎用 |
| marker | 标记 / 标注 | 标记（协议解码的事件标记，不与光标混用） |
| trigger | 触发（绝对主流） | 触发 |
| pulse width | 脉宽（主流） / 脉冲宽度 | 脉宽（面板标签短）；说明文字用"脉冲宽度" |
| period / cycle | 周期 / 循环周期 | 周期 |
| duty cycle | 占空比（主流） / 占空度（少见） | 占空比 |
| frequency | 频率 | 频率 |
| protocol decoder | 协议解析器（KingstVIS 用法） / 协议解码器（sigrok/PulseView 用法） | 协议解码器（与国际接轨）；帮助里注明"又称协议解析器" |
| sample rate | 采样率 | 采样率 |
| sample depth | 采样深度 / 存储深度 | 采样深度（教程原文） |
| threshold voltage | 阈值电压 / 门限电压 | 阈值电压 |
| zoom / pan | 缩放 / 平移（拖动）；也有"左右移动波形" | 缩放 / 平移 |
| annotation | 注释 / 标注 | 标注 |
| measurement panel | 测量窗口 / 测量面板 | 测量面板；与"协议解析"分栏 |

（注：上表 15 行；"游标/标记/标尺"的实际使用频率**未找到公开统计资料**，建议基于"光标"在 KingstVIS 与 sigrok 中文教程中的用例按上表选择，并在产品内保持一致。）

## 5. 8 个必查点的结论汇总

| # | 问题 | 结论 | 来源 |
|---|---|---|---|
| 1 | 时间轴刻度怎么标（单位、密度） | OLS：时间轴独立组件高 30px，20px 步进，长刻度每 10 格打标签、短刻度每 20 格只画线（原文 LONG_TICK_INTERVAL=10 / TIME_INTERVAL=20，实际代码中长刻度更稀疏），刻度间隔随缩放自适应；时间以触发点为零点，标签经 DisplayUtils 自动选 s/ms/μs/ns/ps 且 3 位小数。KingstVIS：波形区上方有时间轴，但刻度密度/单位**未找到公开资料**（仅知存在）。 | [A1] DiagramTimeLineUI.java / DisplayUtils.java；[B2][B3]（仅确认时间轴存在） |
| 2 | AB 光标的交互（放置、拖动、数值显示） | OLS：右键菜单 `Set Cursor N` 放置，光标数 MAX_CURSORS 个；菜单支持跳首/末/上/下/指定编号/触发点；`SetCursorModeAction` 开关光标模式（助记 C）；光标位置改变触发 `DiagramCursorChangeListener` 重画；时间轴旗标上画光标时间文本；测量面板有 cursorA/cursorB 下拉框任选两条光标。KingstVIS：未找到 AB 双光标资料，只有鼠标悬停式测量与边沿居中。 | [A1] SetCursorAction/SetCursorModeAction/DiagramTimeLineUI/MeasurementDialog；[B2][B3] |
| 3 | 区间测量能算哪些量 | OLS：AB 间距→时间差（distance）与频率（1/间距）；另有自动测时钟频率/占空比。KingstVIS（鼠标所在脉冲）：脉宽、周期、占空比、频率四项。 | [A1] MeasurementDialog；[B1][B3] |
| 4 | 测量面板的信息密度（一屏能看多少数据） | OLS：非模态对话框，每个光标一行时间值 + A/B 间距 + 频率 + 自动时钟频率 + 占空比，约 10+ 行，记忆上次选择；KingstVIS：右侧分析栏集成测量（4 项，可勾选启用）、解码设置、解码结果，密度高但可控。 | [A1] MeasurementDialog；[B2][B3] |
| 5 | 中文界面的术语习惯 | 教程原文使用：工具栏、阈值电压、通道设置栏、波形显示窗口、采样结果分析窗口、测量窗口、协议解析器、时间轴、滚动条、脉宽/周期/占空比/频率；"光标/游标/标尺"的确切使用频率**未找到公开统计**，教程未强调命名游标，测量以"当前位置脉冲"表述。 | [B2][B3]；[A5] |
| 6 | 快捷键设计 | OLS：`SetCursorModeAction` 设 MNEMONIC_KEY=VK_C（菜单助记 C）；其余动作有 ID 但具体键绑**未找到公开资料**。KingstVIS：教程只写鼠标操作，未列键盘快捷键，**未找到公开资料**。 | [A1] SetCursorModeAction；[B2][B3] |
| 7 | 颜色/主题 | OLS：`DiagramSettings` 提供 getBackgroundColor()/getTimeColor() 等，颜色可配置；具体配色值**未找到公开资料**。KingstVIS：未找到公开资料。 | [A1] DiagramTimeLineUI/DiagramSettings；[B2][B3] |
| 8 | 有没有我们没想到但很实用的功能 | 有：①鼠标悬停即测当前脉冲（KingstVIS）；②上一/下一边沿一键居中（KingstVIS）；③任意两光标组成 AB 且选择被记忆（OLS）；④自动估算时钟频率/占空比（OLS）；⑤测量面板定时刷新、非模态常驻（OLS）；⑥解码器/输出用 `key=value` 串文本化配置、便于复现（sigrok-cli）；⑦全功能演示模式（KingstVIS）。 | [A1][A3][B1][B2][B3] |

## 6. 独有的好点子（我们没想到的）

（≥5 条，每条说明为什么好）

1. **鼠标悬停式"当前脉冲"测量**（[B3]）——用户无需先学放光标，指哪测哪；可作为我们 AB 测量之外的默认快速模式，降低"功能太少"的感知门槛。
2. **边沿居中按钮**（[B2][B3]）——"把前/后一个边沿移到中心"直接对应"我要看这个跳变"的意图，比无目的缩放平移高效；实现只需在采样数组里找最近边沿并重设视口。
3. **任意编号光标两两组合 + 记忆选择**（[A1]）——比固定 A/B 灵活，且下次打开保持上次选择，减少重复配置。
4. **自动时钟频率/占空比测量按钮**（[A1]）——对晶振/PWM 信号一键出结果；与手动 AB 互补，能立刻多出两个" measurable"功能点。
5. **非模态测量面板 + 500ms 定时刷新**（[A1]）——拖动/缩放时光标与读数同步变化，形成"操作-反馈"闭环，不用来回点确认。
6. **协议链的文本化配置串**（[A3]）——`uart:baudrate=115200:parity=odd` 这类表达既便于 UI 展示，又能复制粘贴、写入工程文件、脚本复现，还天然支持多解码器串联。
7. **全功能演示模式**（[B1]）——没有硬件也能让用户/我们演示测量与解码，适合教学与售前。
8. **把采样率经验法则做成预设提示**（[B3]）——9600→50kHz、115200→1MHz 这类速查表可直接嵌进采样设置对话框，减少"我设的采样率对不对"的困惑。

## 7. 与我们的差距表

| 能力 | 我们现状 | OLS Java 客户端 [A1] | KingstVIS [B1][B2][B3] | 是否建议补 |
|---|---|---|---|---|
| 时间轴独立组件/刻度自适应 | 已有基本显示（待核对密度/单位） | 独立 DiagramTimeLine，刻度随缩放自适应，触发点为零点 | 波形区有时间轴，细节未公开 | 补：触发点作零点、单位自动缩放、长/短刻度分级 |
| AB 区间测量 | **缺**（本次要补） | 任意两光标→时间差+频率 | 未见 AB，只有鼠标悬停式测量 | 补：AB 光标 + 时间差，顺带 1/间距=频率 |
| 光标导航（首/末/上/下/触发点） | 部分（已有光标） | 完整动作族 | 边沿居中按钮 | 补：跳触发点、上一/下一边沿居中 |
| 鼠标悬停即测当前脉冲 | 缺 | 无（依赖光标） | 有：脉宽/周期/占空比/频率 | 补：作为快速测量模式 |
| 自动测时钟频率/占空比 | 部分（已有频率/占空比） | 有独立 Measure Clock 按钮 | 有（基于当前脉冲） | 视情况：做成一键按钮 |
| 测量面板刷新方式 | 待核对 | 非模态 + 500ms Timer 自动刷新 | 随鼠标位置更新 | 补：实时刷新 + 可勾选测量项 |
| 协议解码配置表达 | 已有 GUI 配置（UART/I2C/SPI/CAN） | 各协议独立 Analyzer 对话框 | 右侧"协议解析器"配置 | 补：文本化参数串，便于复现/分享 |
| 演示模式 | 缺 | 未找到资料 | 有（全功能 demo） | 可选 |
| 中文术语一致性 | 待核对 | 无中文界面 | 工具栏/测量窗口/协议解析器等 | 统一用"光标/刻度/测量面板/协议解码器" |

**未覆盖项 / 风险**：
- 契约给的 2 个 GitHub 链接与 sigrok wiki OLS 页 404，已用实际存在的 `GadgetFactory/ols` 等替代；这些链接本身已失效，报告中如实注明。
- KingstVIS 手册 PDF [B4] 未逐页核对；DSLogic 独立上位机界面、Saleae Logic 1.x 界面、B 站视频操作细节均**未找到公开资料**，未编造。
- "游标/标记/标尺"的实际使用频率无公开统计，术语建议基于教程用例与一致性原则，属推断而非实证。
- OLS 时间轴代码中 `LONG_TICK_INTERVAL=10` 与 `TIME_INTERVAL=20` 的语义（哪个对应长刻度标签）需看完整 `paint()` 才能定论，报告按"长刻度更稀疏、打标签"描述，标注了不确定性。
