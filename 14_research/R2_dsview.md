# DSView 功能调研

> 调研对象：DreamSourceLab DSView（基于 sigrok 的开源逻辑分析仪/示波器上位机，GPLv3+）
> 调研目的：为自研 8 通道逻辑分析仪上位机提取「可照着实现」的 GUI/交互功能清单。
> 调研方式：GitHub API 抓 README、NEWS 变更日志、ug31.pdf 官方用户手册（63 页）、源码头文件；dreamsourcelab 官网下载页。所有结论均标注一手依据，查不到即写「未找到公开资料」。

## 0. 资料来源（实际 fetch 成功的 URL）

以下 URL 均实际抓取成功（HTTP 200，通过 curl / GitHub API；WebFetch 对 github/dreamsourcelab 多次超时或 403，故改用 curl + GitHub API）：

1. `https://github.com/DreamSourceLab/DSView` —— 仓库主页，curl HTTP 200
2. `https://api.github.com/repos/DreamSourceLab/DSView` —— 仓库元数据（1455 stars，default_branch=master，2026-11 仍活跃）
3. `https://api.github.com/repos/DreamSourceLab/DSView/readme` —— README（DSView 基于 sigrok，GPLv3+，状态为 "usable but work in progress"）
4. `https://api.github.com/repos/DreamSourceLab/DSView/contents/` —— 根目录清单（发现 NEWS25 / NEWS31 / ug25.pdf / ug31.pdf / doc / DSView）
5. `https://api.github.com/repos/DreamSourceLab/DSView/releases?per_page=20` —— releases（v1.3.0~v1.3.2 等，最新官方安装包 v1.3.2 / 2024-04）
6. `https://api.github.com/repos/DreamSourceLab/DSView/contents/NEWS31` —— 英文变更日志（20KB，v0.4.0~v1.3.2，**功能演进主证据**）
7. `https://api.github.com/repos/DreamSourceLab/DSView/contents/NEWS25` —— 中文变更日志（21KB，与 NEWS31 对应）
8. `https://api.github.com/repos/DreamSourceLab/DSView/contents/ug31.pdf` —— 官方用户手册（63 页，pdftotext 提取 2532 行，**UI 布局与交互主证据**）
9. `https://www.dreamsourcelab.com/download/` —— 官网下载页（确认最新版本 DSView V1.3.2，内嵌 changelog）
10. `https://api.github.com/repos/DreamSourceLab/DSView/git/trees/master?recursive=1` —— 全源码树（354KB，用于模块文件名划分分析）
11. `https://api.github.com/repos/DreamSourceLab/DSView/contents/DSView/pv/view/ruler.cpp` —— 时间轴刻度算法源码
12. `https://api.github.com/repos/DreamSourceLab/DSView/contents/DSView/pv/view/view.cpp` —— 缩放/坐标变换源码
13. `https://api.github.com/repos/DreamSourceLab/DSView/contents/DSView/pv/dock/measuredock.cpp` —— 测量面板源码
14. `https://api.github.com/repos/DreamSourceLab/DSView/contents/DSView/pv/view/{cursor,xcursor,ruler,view,viewport}.h`、`.../dock/measuredock.h`、`.../dialogs/regionoptions.h` —— 类接口定义

**抓取失败（如实记录）**：`raw.githubusercontent.com/*`（ECONNRESET）、`https://www.dreamsourcelab.com/doc/`（HTTP 403，无公开文档页；文档实际以仓库内 `ug31.pdf`/`ug25.pdf` 提供）、WebFetch 直连 github/dreamsourcelab（多次 60s 超时）。

**源码模块文件名划分（`DSView/pv/` 下，文件名即功能划分）**：
- `view/`：`ruler.*`（时间标尺）、`cursor.*` + `xcursor.*`（水平/垂直光标）、`timemarker.*`、`viewport.*`、`view.*`（总视图）、`logicsignal.*`/`analogsignal.*`/`dsosignal.*`/`groupsignal.*`（各通道类型）、`decodetrace.*`（解码行）、`mathtrace.*`/`spectrumtrace.*`/`lissajoustrace.*`（数学/频谱/李萨如）、`header.*`（通道头）、`selectableitem.*`、`viewstatus.*`
- `dock/`：`measuredock.*`（测量）、`protocoldock.*`（协议）、`searchdock.*`（搜索）、`triggerdock.*`/`dsotriggerdock.*`（触发）
- `dialogs/`：`search.*`、`regionoptions.*`（区域）、`protocollist.*`/`protocolexp.*`（解码列表/导出）、`mathoptions.*`、`fftoptions.*`、`storeprogress.*`
- `toolbars/`：`filebar.*`、`logobar.*`、`samplingbar.*`、`trigbar.*`、`titlebar.*`

---

## 1. 界面布局全景（ASCII 图 + 分区命名）

依据 ug31.pdf §1.4（Figure 1-2 逻辑分析仪模式）。DSView 采用 Qt5 DockWidget 布局，与 PulseView 同源（源代码版权行写明 "DSView is based on PulseView"）。

```
┌──────────────────────────────────────────────────────────────────────┐
│ TitleBar: [设备类型图标: USB2/USB3/Demo/File] [设备名] [采样率]        │
│            [采样时长] ───── Toolbar(Sampling/Trigger/File) ── [Help]  │
├─────────────┬──────────────────────────────────────────┬─────────────┤
│ Device Mode │  时间标尺 Ruler (刻度 + 光标标签 + T触发标) │             │
│ 切换栏      ├──────────────────────────────────────────┤  Tool Dock  │
│ (LA/DSO/    │  ┌────────────────────────────────────┐  │  (可折叠/   │
│  DAQ)       │  │ Channel  逻辑波形 Wave Window       │  │   可拖动)   │
│             │  │ Header │  Ch0 ─┐   ┌─              │  │  ┌────────┐ │
├─────────────┤  │ [色/名]│  Ch1  └─┐ └─┐             │  │  │Measure│ │
│ Channel     │  │ [序号] │  Ch2 ───┘  └─             │  │  │Trigger│ │
│ Options     │  │        │  DecodeRow: I2C: S 0x48 A │  │  │Decoder│ │
│ (通道显隐/  │  │        │  DecodeRow: UART: "Hello" │  │  │Search  │ │
│  名称/颜色) │  └────────────────────────────────────┘  │  └────────┘ │
│             │  ├─ 水平滚动条 ScrollBar (大范围跳转) ────┤             │
│             │  └─ [Pattern Search 搜索框(底部)]        │             │
└─────────────┴──────────────────────────────────────────┴─────────────┘
```

分区命名（官方术语）：Titlebar / Device Mode / Channel Options / Ruler / Wave Window / Tool Dock / Scroll Bar / Pattern Search。示波器模式额外有 FFT Window 与 Measurements 显示盒；DAQ 模式为多 Wave Windows。

**我们可以怎么抄**：
- 采用「左侧通道头 + 中央视口 + 顶部标尺 + 右侧可折叠 Dock + 底部滚动条」五区布局，通道头与视口共享同一个垂直坐标映射（DSView 中 `header` 与 `viewport` 都由 `View` 拥有）。
- Dock 用可停靠/可折叠框架实现，测量/触发/解码/搜索各自独立，用户可拖到任意位置；v1.3.2 修复了「跨屏拖动窗口崩溃」并新增「原生窗口拖拽与排列」，说明 DSView 很看重多显示器场景，抄的时候要一开始就把 dock 位置序列化进设置。
- 工具栏按「设备信息 | 采样 | 触发 | 文件 | 帮助」分组，设备类型图标常驻最左（USB2/USB3/Demo/File 四种状态）。

---

## 2. 时间轴

### 2.1 外观与刻度
- Ruler 位于波形窗口顶部，绘制主刻度（Major）+ 次刻度（Minor），次刻度间隔常量 `MinPeriodScale = 10`（即每 10 个次格一个主刻度）。
- 刻度周期候选来自 `ScaleUnits = {1, 2, 5}`（1-2-5 序列），配合 SI 前缀数组（9 档，覆盖 p/n/µ/m/…）与频率前缀数组；精度 `pricision = 2`（保留 2 位小数）。
- 标尺上同时绘制：普通光标标签（可编号）、触发光标固定标签 `'T'`、搜索光标固定标签 `'S'`。
- v1.3.2「修改光标的颜色分配，提高清晰度」——用 22 色 HSB 表 `CursorHsbColorTable[22]` 按光标序号取色（`GetColorByCursorOrder`），避免多光标同色混淆。

### 2.2 缩放与滚动行为
- 滚轮缩放：`zoom(steps)` 以视口中心为锚点；核心公式 `_scale *= pow(1.5, -steps)`（注意步长**底数是 1.5 而非 2**），再 clamp 到 `[_minscale, _maxscale]`。
- 锚点保持：缩放前后保持鼠标所指的采样索引不动，公式为
  `_offset = floor((_offset + offset) * (_preScale / _scale) - offset)`，其中 `offset` 为鼠标在视口中的像素 x；再 clamp 到 `[get_min_offset(), get_max_offset()]`。
- 三种缩放交互（ug31 §2.6.2）：滚轮缩放；**右键拖拽画矩形→区域放大到满窗**；右键双击在「最大缩小状态」与「上一次缩放状态」间切换（zoom toggle）。
- 三种平移交互（ug31 §2.6.1）：左键拖拽波形；**快速甩动+释放触发惯性滚动**（dynamic/loop scrolling，可在 Display Options 开关）；拖底部滚动条大范围跳转；`PageUp/PageDown` 翻页。
- 坐标变换：`index2pixel(index)` 与 `pixel2index(pixel)` 成对，所有光标/测量都基于采样索引（uint64_t）而非浮点时间，避免长时间捕获精度丢失。
- v1.3.0 新增「stream 模式实时显示」「loop 滚动模式」「repeat 模式保留上一屏波形」。

### 2.3 我们可以怎么抄（刻度自适应算法级）
从 `ruler.cpp::draw_logic_tick_mark` 提炼的算法：

```
1) abs_min_period = 10 / cur_snap_samplerate      // 一个采样周期×10
   min_width = 32px; MinValueSpacing = 16px
2) cur_period_scale = ceil(scale * min_width / abs_min_period)
   min_period = cur_period_scale * abs_min_period  // 最小主刻度周期，与采样率对齐
3) order = floor(log10(scale * view_width))        // 当前视口总时长数量级
   prefix = (order - FirstSIPrefixPower) / 3       // 决定 SI 前缀
4) typical_width = 文本宽度(format_time(offset*scale, prefix)) + 16
   tick_period = 0; while typical_width > tick_period/scale: tick_period += min_period
   // 关键：用「像素文本宽度」而非固定数量级判断，保证标签不重叠
5) minor = tick_period / 10
6) first_major = floor(offset*scale / tick_period)
   first_minor = floor(offset*scale / minor + 1); t0 = first_major*tick_period
7) 逐格绘制：主格画完整标签(居中)；次格仅当 minor/scale > 2*typical_width
   或 > 1.1*inc_text_width 时才画标签，否则只画线  // 次标签防重叠双阈值
```

- 关键借鉴点：①刻度周期**向上取整到采样周期整数倍**，保证刻度落在真实采样点上；②标签宽度用 `QPainter::boundingRect` 实测，而非估算字符数；③次刻度标签有独立防重叠阈值。
- 缩放核心照抄 `_scale *= pow(1.5, -steps)` 和 offset 补偿公式，配合「鼠标锚点不漂移」的体验。

---

## 3. 光标与测量（DSView 的强项，写最详细）

### 3.1 光标数量、类型与编号
- 水平光标（时间光标 `Cursor : TimeMarker`）：**任意多个**，用 `std::list<Cursor*> _cursorList` 管理；`add_cursor(color, sampleIndex)` 按序添加；删除后**剩余光标自动重新编号**（ug31 §2.7.8 "remain cursors will be renumbered"）。
- 垂直光标（电压光标 `XCursor`）：DSO 模式专有，枚举 `XCur_type { XCur_Y, XCur_X0, XCur_X1 }`，含 Y 值、X0/X1 两组值，可绑定到某个 DsoSignal 通道。
- 特殊光标两条：触发光标 `_trig_cursor`（标签 `'T'`）、搜索光标 `_search_cursor`（标签 `'S'`），单独管理。
- v0.9.7 变更：「improve cursor measurement method, add **16 sets of measurement between cursors**」——测量面板可同时挂 16 组光标间测量（距离/边沿计数），这是 DSView 相对 PulseView 的核心优势。

### 3.2 插入、拖动、跳转、删除
- 插入方式一：波形区**双击左键**插入光标（ug31 §2.7.4）。
- 插入方式二：时间标尺区左键单击→出现向下箭头带→带内再左键单击插入。
- 拖动：光标加粗高亮时左键按住拖动；**靠近通道边沿自动吸附（auto snap to edge）**——v0.9.7「add auto snap to edge function when insert cursor」。
- 标尺区快捷操作：左键在任意位置单击显示所有已有光标的编号，点某编号即可把对应光标移到此处；**右键单击显示编号菜单→点编号跳转到该光标位置**（Cursor Jump，§2.7.6）。
- 删除：点光标上的 `'×'` 区域删除，其余重新编号。
- v0.9.8「improve move operations of cursors/label/trigger level, support both press-drag and select-move-release mode」——同时支持「按住拖」和「选中-移动-再点放下」两种范式。

### 3.3 ΔT 与 1/ΔT（频率）
- 标尺类提供成对格式化函数：`format_time(t, prefix)`、`format_freq(period)`、`format_real_time(delta_index, sample_rate)`、`format_real_freq(delta_index, sample_rate)`。
- 测量面板鼠标区实时显示四项：**width / period / frequency / duty cycle**（源码 `measure_updated()` 循环里 `_view.get_measure("width"|"period"|"frequency"|"duty")`），频率即周期倒数 1/T。
- 距离测量（Distance Measure）显示两光标间的**时间或采样数**；边沿计数（Edges Counter）显示两光标间指定通道的上升/下降/总边沿数。
- 频率测量算法经历多轮改进：v1.0.0「improve algorithm of frequency measure, especially for low frequency and special signals」、v1.0.0「improve measure of frequency, refer to current trigger level」。

### 3.4 多光标对比
- 测量面板第三个 GroupBox「Cursors」列出所有光标及其时间点（`build_cursor_pannel()`、`cursor_update()`、`popup_all_coursors()`），可逐个选中/删除，光标颜色由序号决定，与波形区光标标签颜色一致。
- v1.3.1「fix trigger position display in repeat mode」「fix mouse measurements in repeat mode」——重复/循环模式下测量仍跟随最新数据更新。

### 3.5 我们可以怎么抄
- 数据结构用「采样索引 uint64_t + 序号 order + 颜色表按序取色」，不用浮点时间做主键；删除后重排 order 并重算颜色。
- 光标命中测试：命中区 = 标尺上的标签矩形 `get_label_rect` + 视口中的竖线邻域；拖动中若鼠标 x 距某边沿 < 吸附阈值（建议 = 当前像素/采样比 × 常数），则 index 吸附到该边沿采样点。
- 实现「选中-移动-再点放下」与「按住拖」双模式：维护 `grabbed` 状态机（`set_grabbed` / `rel_grabbed`），第一次点击置 grabbed，移动更新 index，第二次点击释放。
- 频率显示用 `1/(Δindex/sampleRate)`，并复用同一套 SI 前缀格式化（时间 p~s、频率 Hz~GHz），低频率时按 v1.0.0 经验引入触发电平作为参考点。

---

## 4. 测量表

- 逻辑分析仪模式：**MeasureDock**（ug31 §2.7.7，快捷键 `M`）含 4 组：
  1. `Mouse measurement`（鼠标悬停测量）带「Enable floating measurement」开关，实时显示 width / period / frequency / duty；
  2. `Cursor Distance`——可点 `+` 添加任意多组，每组选 start/end 光标，显示时间或采样数；
  3. `Edges`——可点 `+` 添加任意多组，每组选 start/end 光标 + 通道号，显示 Rising/Falling/Edges；
  4. `Cursors`——列出所有光标及时间点，可跳转/删除。
- 示波器模式：**Auto Measurement** 支持 **20 个参数、10 个显示盒**，每个显示盒可独立选通道与参数，设置自动持久化（ug31 §3.4.1；v1.0.0「support up to 20 measurements」）。20 个参数官方手册未逐一列出名称，仅枚举数量；宽度/周期/频率/占空比/RMS/均值/峰峰值/脉冲数等见 v0.9.4~v1.3.2 变更日志。
- 既有实时（鼠标悬停）也有选区（光标间）两种测量范式。

**我们可以怎么抄**：测量面板做成「行列表格 + 每行下拉选择（通道、起始光标、结束光标、量类型）」，行可增删；数据更新走统一信号 `measure_updated()`，由 View 计算后回填各 QLabel；把「鼠标浮动测量」做成独立开关，避免鼠标经过时面板抖动。存储时把每组测量的定义（而非结果）序列化，重开自动恢复。

---

## 5. 区域选择

- **波形缩放选区**：右键按住拖拽画矩形→松开后选区放大到满窗（ug31 §2.6.2 "Window zoom"）。
- **测量选区**：在通道高/低电平之间左键按下→拖动→动态显示区间内边沿计数，再左键完成（ug31 §2.7.2 Pulse Counter）；边沿距离测量同理（§2.7.3）。
- **解码区域**：RegionOptions 对话框（`dialogs/regionoptions.h`）用两个 ComboBox 选起止光标作为 decode region，避免全量解码耗时（ug31 §2.8.1；v0.9.6「add start and end settings for protocol decoders」）。
- **区域波形保存/导出**：v1.3.2 新增「Add region waveform save and export feature」。
- 区域解码进度显示（v1.0.0「fix progress display issue when set region decode」）说明长选区解码有进度反馈。

**我们可以怎么抄**：统一一个 `Region{startIndex, endIndex}` 结构，来源可为「光标对 / 右键矩形 / 拖拽测量」；所有区域操作（缩放、解码、导出、统计）消费同一 Region。选区绘制用半透明矩形 + 两端时间标签；解码时先按 Region 裁剪样本再送解码器，并显示进度条。

---

## 6. 信号统计

- 逻辑分析仪侧：**基于光标的边沿统计**（v0.9.7「add cursor-based edge statistics function」）与测量面板 Edges Counter 组（指定通道、两光标间，统计上升/下降/总边沿数）。
- 脉冲计数（ug31 §2.7.2）动态显示区间内 edges / rising / falling 三数。
- v1.2.0 示波器「remove invalid edge count measurement display」、v1.3.2「Improve pulse count measurement accuracy」——计数精度持续打磨。
- **未找到公开资料**：DSView 是否有类似 Saleae「选区内信号的频率分布/协议统计直方图」那样的独立统计面板——在用户手册、变更日志、源码文件名中均未发现通用 statistics 面板，只有上述边沿/脉冲计数。

**我们可以怎么抄**：把「选区统计」做成测量表的衍生视图：给定 Region 与通道，一次扫描样本计算边沿数、上升/下降数、周期/频率均值与抖动、占空比均值；结果既可列表也可简易直方图。复杂度 O(选区采样数)，扫描边沿时同时累加各量，避免多次遍历。

---

## 7. 解码联动

- **排列方式**：解码结果以独立「解码行（DecodedTrace / annotation rows）」**叠加在波形窗口下方**，每条协议占一行，多层协议自动堆叠（v1.2.0「add auto stacking function when adding multi-layer protocols」）；v1.3.0 支持「解码器与波形通道任意排序并记忆」。
- **独立面板**：Protocol List Viewer（快捷键 `D` 打开 Decoder Dock，含 Decoder Select + Protocol List Viewer 两部分，ug31 §2.8），以表格列出每条解码结果（时间、通道、值）。
- **双向联动**（核心）：点击列表行→波形窗口跳到对应位置（"click on any row of the list viewer can map to the same location in the wave window"）；v0.9.7「add mapping function from graphic decode to list decode」「add mapping flag between graphic decode and list decode」——波形上点解码 annotation 也能反向定位到列表行。
- **搜索联动**：列表支持单行文本搜索与多字节数据搜索（v1.3.2「fix multi-byte search crash」），Previous/Next 跳转且波形同步定位；可指定起始行（ug31 §2.8.4）。
- 解码器数量 138+（v1.2.0），支持 stack decoder（如 24xx EEPROM 基于 I2C）、解码结果多列导出到同一 CSV（v1.3.0）。

**我们可以怎么抄**：解码结果用「annotation 行」渲染，每行一组 `{startSample, endSample, label, color}`；列表视图与波形共用同一 annotation 索引，点击行→`set_scale_offset` 定位到该样本附近，点击波形 annotation→列表滚动到对应行（维护 `annotationId` 双向映射）。搜索先过滤 annotation 列表再高亮，Previous/Next 本质是对过滤结果的游标移动。

---

## 8. 多视图 / 数学通道

- DSView 是**多设备模式**架构（LA 逻辑分析仪 / DSO 示波器 / DAQ 数据采集），不是把数字+模拟+数学通道无差别同屏：
  - LA 模式：数字通道 + 解码行 + GroupSignal（分组信号，v0.9.5 提到 group signal）。
  - DSO 模式：模拟通道 + **FFT Window**（频谱分析）+ **Math Channel** + Lissajous（李萨如）窗口（ug31 §3.5~§3.7）。
- 数学通道（ug31 §3.6）：Function→Math 打开 Math Options，勾选 Enable；**支持 Add/Sub/Mul/Div 四则运算**（v1.0.0「implement Add/Sub/Mul/Div math channel」）；数学通道可像物理通道一样改垂直刻度（旋钮）、颜色、偏移（拖通道标签），时基可独立调整（v1.1.0 修复「math channel timebase can't be changed when waiting trigger」）。
- 频谱：FFT 参数可配（v1.3.2 修复采集中改 FFT 参数崩溃），频谱作为独立 trace 与波形同屏。
- **未找到公开资料**：DSView 在纯逻辑分析仪模式下把模拟通道与数字通道混合同屏的能力——官方手册中数字与模拟分属不同 Device Mode。

**我们可以怎么抄**：视图层抽象出统一 `Trace` 基类，派生 `LogicSignal / AnalogSignal / MathTrace / SpectrumTrace / DecoderTrace`，共用同一 Ruler 与 View 坐标系统；这样数学通道、解码行与数字波形天然同屏、同缩放。若只做数字逻辑分析仪，可先只实现 LogicSignal+DecoderTrace+MathTrace（对捕获的脉宽/频率序列做简单运算），四则数学通道留作二期。

---

## 9. 波形导航条

- **未找到公开资料**：DSView 没有 Saleae/PulseView 式的独立「Overview Bar / 缩略导航条」——源码树中无 `overview`/`navigator` 相关文件，用户手册也没有该部件描述。
- 替代方案：底部**水平滚动条**承担大范围导航（ug31 §2.6.1 "Large range: Drag the scroll bar in window bottom will quickly jump to a certain position"）；配合惯性甩动滚动、PageUp/PageDown、模式搜索（Pattern Search，`R`）定位特定边沿/图形。
- v0.9.8「fix out of boundary issue of scroll bar, when sample depth greater than 8G」——大数据量下滚动条范围管理有专门处理。

**我们可以怎么抄**：一期可不做缩略图 overview bar，用「底部滚动条 + 当前视口在总采样中的位置指示条（细矩形滑块）」即可覆盖大部分导航需求；二期若要 overview，用对原始采样做 min/max 抽取（每 N 个点保留一对极值）生成缩略波形，点击/拖拽缩略图→映射到主视口 offset，复用 `index2pixel` 的逆变换。

---

## 10. 触发系统

- **硬件触发为主**（DSView 面向 DSLogic/DSCope 硬件）：
  - Simple Trigger（简单触发）：单/多通道的边沿或电平触发，多通道条件为逻辑「AND」，可设触发位置百分比（快捷键 `T` 打开 Trigger Dock，ug31 §2.4.2）。
  - Advanced Trigger（高级触发）：仅 Buffer Mode 可用，含 **Stage Trigger（最多 16 级事件条件）** 与 **Serial Trigger（串行值触发，带计数器）**，支持协议内容触发（例：I2C 上出现 0b010000100、SPI 上出现 0x1234，ug31 §2.4.3）。
  - 支持最多 32 通道触发（v1.1.0「extend channel support for trigger up to 32 channels」）、触发计数器从 16bit 升到 32bit（v0.9.4）。
- **触发位置标记**：触发位置按采样时长百分比设置（10% 观察触发后，90% 观察触发前，ug31 §2.4.1 Figure 2-13）；标尺上绘制触发光标 `'T'` 标签；v1.3.1 修复重复模式触发位置显示、v0.9.7 修复触发位置显示问题；v0.9.6「add display of trigger time」。
- **软件触发 / 后置触发**：DSView 的「repeat/loop 模式 + 模式搜索」可实现类似软触发的重复捕获与定位，但没有明确的纯软件触发配置项——**软件触发在公开资料中未找到独立功能描述**。
- 流模式下触发位置固定约 1%（硬件限制，ug31 §2.4.1 注）。

**我们可以怎么抄**：一期只做软件触发（在已采集样本中按通道边沿/电平/简单模式匹配定位触发点），UI 复用「触发位置 %」滑杆；捕获后把触发点索引传给 View，在标尺上画 `'T'` 标记，并让 `offset` 默认对齐到「触发点落在视口 10%~90% 指定位置」。高级串行触发作为二期，实现时按「状态机 + 每级条件（通道/边沿/值/计数）」建模，正好对应 Stage Trigger 16 级。

---

## 11. UI 细节

- **主题**：dark / light 双主题，Display→Themes 动态切换（v1.0.0 新增，ug31 §1.4.4）。
- **语言**：中文/英文，Help→Language 动态切换（v1.0.0「add multi-language support and dynamic switch」；v1.3.0 改多语言框架支持扩展）。
- **侧栏可折叠/可拖动**：Trigger / Measure / Decoder / Search 均为 DockWidget，可拖动、可停靠、可折叠；v1.2.0 修复「hidden toolbar buttons」「window cannot be recovered after moving out of screen」，v1.3.2 增加跨屏拖动与窗口排列支持。
- **字体/DPI**：v1.3.0 支持界面字号设置与实时切换；v1.1.1/v1.3.2 用 SVG 图标改善高 DPI，适配 4K 与 DPI≥1.5@1080P。
- **快捷键**（ug31 汇总）：`T` 触发、`M` 测量、`D` 解码器、`R` 搜索、`O` 选项、`S` 开始采集、`I` 单次采集、`PageUp/PageDown` 平移、`0/1` DSO 通道聚焦、`↑/↓` 调旋钮；v1.2.2 增加 Ctrl/Shift/Alt 组合键识别。
- 会话保存/加载（v0.9.4）、日志查看与清除（v1.3.0）、截图、CSV/VCD/gnuplot/zip 导出（v0.9.3+）。

**我们可以怎么抄**：主题与语言都做成「运行时可切换 + 配置持久化」，所有文本走翻译表（L_S 宏风格）、所有颜色走主题表（不要硬编码 QColor）；Dock 位置/开关状态写入设置文件；快捷键集中注册到一张快捷键表，便于后续自定义；图标用 SVG 以支持高 DPI。

---

## 12. PulseView vs DSView 交互对比

（DSView 源码版权行明确 "DSView is based on PulseView"，是PulseView 的分支再发展；下表基于 ug31、NEWS 与 PulseView 公开常识对比，后者非本次一手 fetch 对象，标注为依据常识）

| 维度 | PulseView | DSView | 谁更好 / 为什么 |
|---|---|---|---|
| 测量 | 主要是两点光标 + 简单测量 | 多光标（任意个）+ 16 组光标间测量 + 鼠标浮动测量 + 20 项自动测量(DSO) | **DSView**：测量密度和实时性显著更强 |
| 光标交互 | 拖拽为主 | 双击插入、标尺箭头插入、边沿吸附、编号跳转、两种拖动范式、删除自动重排 | **DSView**：交互路径更完整 |
| 解码展示 | 波形下叠加注解行 | 叠加注解行 + List Viewer + 双向点击联动 + 文本/多字节搜索 + 138 解码器 + 自动堆叠 | **DSView**：联动与检索能力更强 |
| 刻度算法 | 1-2-5 序列 + SI 前缀 | 同样 1-2-5，但按采样周期取整 + 实测文本宽度防重叠 + 双阈值次标签 | **DSView**：长时间/大数据量下标签更稳 |
| 触发 | 依赖 sigrok 设备能力，软件复杂触发有限 | 硬件简单/高级触发（16 级 Stage + Serial）、触发位置%、'T' 标记 | **DSView**（若我们有硬件触发需求）：更贴近工程调试 |
| 主题/多语言 | 较简单 | dark/light、中英动态切换、多 DPI、SVG 图标 | **DSView**：精致度更高 |
| 架构 | 纯软件、跨设备 | 多 Device Mode（LA/DSO/DAQ）+ 自研设备层 | 各有侧重；DSView 绑定自家硬件 |
| 开源生态 | sigrok 社区大、解码器丰富 | 基于 sigrok 但独立维护、解码器 138+ | PulseView 生态更开放 |

**结论**：用户目标中「界面更精致、测量交互做得更好」的判断得到一手资料支持——差距集中在**测量面板的组织方式（多组可增删测量行）**、**光标交互的完整度（吸附/跳转/重排/双拖动范式）**、**解码列表双向联动**三处。

---

## 13. 优先级建议（成本/价值四象限）

**高价值 / 低成本（一期必做）**
1. 光标测量面板：多组「起点光标-终点光标-量类型」可增删测量行（§4）——直接命中 DSView 强项。
2. 光标边沿吸附 + 删除重排 + 按序取色（§3）——体验提升明显、实现简单。
3. 刻度防重叠算法（§2.3）——照抄 `ruler.cpp` 20 行逻辑即可。
4. 滚轮以鼠标为锚点缩放（底数 1.5）+ 右键矩形放大 + 惯性平移（§2.2）。
5. 区域统一结构 Region + 区域解码/导出（§5）。

**高价值 / 中成本（二期）**
6. 解码 List Viewer + 波形↔列表双向联动 + 搜索（§7）。
7. 选区信号统计（边沿/频率/占空比直方图，§6）。
8. 软件触发 + 触发位置标记（§10）。

**中价值 / 中成本（三期）**
9. dark/light 主题 + 配置持久化（§11）。
10. 多光标对比表（Cursors 组，§3.4）。

**低价值 / 高成本（暂缓）**
11. Overview 缩略导航条（§9）——滚动条+位置指示可先行替代。
12. 硬件高级触发 16 级 Stage / Serial（§10）——依赖硬件能力。
13. 示波器专用 20 项自动测量、Math 四则、FFT、Lissajous（§8/§4）——超出逻辑分析仪范围。

---

## 14. 与我们现有实现的差距表

我们已有：8 通道数字波形、滚轮缩放、平移、光标、采集（200k~24MHz）、软件触发、UART/I2C/SPI/CAN 解码、每通道频率/占空比/脉宽、导出 CSV/VCD。

| 功能点 | 我们现状 | DSView 做法 | 差距等级 | 补齐动作 |
|---|---|---|---|---|
| 时间轴刻度自适应 | 有缩放，刻度算法未确认 | 1-2-5 + 采样周期取整 + 实测文本宽度防重叠 | 中 | 照抄 §2.3 算法 |
| 缩放锚点 | 有滚轮缩放 | 鼠标锚点不漂移，底数 1.5，offset 补偿公式 | 中 | 换公式 |
| 右键矩形放大 / 惯性平移 / 双击缩放切换 | 未确认 | 三种都支持 | 中 | 加交互 |
| 光标数量 | 有光标（数量未确认） | 任意多个 + 自动重排 + 按序取色 | 中 | 改数据结构 |
| 光标边沿吸附 | 未确认 | 自动吸附 | 中 | 加吸附阈值逻辑 |
| 光标跳转/双拖动范式 | 未确认 | 标尺编号跳转、press-drag + select-move-release | 低 | 加状态机 |
| 多组光标间测量表 | **无** | Distance + Edges 任意多组，16 组测量 | **高** | 新增测量 Dock |
| 鼠标悬停浮动测量 | 未确认 | width/period/freq/duty 实时显示 + 开关 | 中 | 加浮动测量 |
| 区域选择统一结构 | 未确认 | Region 供缩放/解码/导出/统计共用 | 中 | 抽 Region |
| 选区内信号统计 | **无** | 光标边沿统计、脉冲计数 | **高** | 新增统计视图 |
| 解码列表 + 双向联动 | 有解码叠加，列表未确认 | List Viewer + 点击互跳 + 搜索 | **高** | 新增列表与映射 |
| 解码区域裁剪/自动堆叠/排序记忆 | 未确认 | 支持 | 中 | 逐步补 |
| 多视图（模拟/数学/频谱） | 仅数字 | LA/DSO/DAQ 分模式，DSO 有 Math/FFT | 低（超范围） | 暂缓 |
| Overview 导航条 | 未确认 | 无独立 overview，用滚动条+Pattern Search | 无/低 | 滚动条位置指示即可 |
| 硬件高级触发（Stage/Serial） | 仅软件触发 | 16 级 Stage + Serial + 触发位置% | 低（依赖硬件） | 暂缓；先补触发位置标记 |
| 主题/多语言/快捷键表 | 未确认 | dark/light、中英、集中快捷键 | 低 | 配置化 |
| 导出 | CSV/VCD | CSV/VCD/gnuplot/zip + 区域导出 + 多列解码同 CSV | 中 | 加区域导出 |

**最值得抄的三件事（一句话）**：①任意多光标 + 可增删多组测量的 MeasureDock；②解码注解行与列表行的双向点击联动；③「文本宽度实测 + 采样周期取整」的时间轴防重叠刻度算法。
