# Saleae Logic 2 功能调研

> 调研对象：Saleae Logic 2（现役商业软件，有免费版），用户「原厂就有的功能」对标基准。
> 调研日期：2026-11-25。方法：官方文档站逐页抓取，未抓取到的内容一律标注，不编造。

## 0. 资料来源（URL + 访问是否成功 + 内容可信度）

**重要说明（站点迁移）**：旧域名 `support.saleae.com` 的所有路径均返回 **302**，跳转到新域名 `www.saleae.com/support`。因此下表把「请求 URL」与「实际取到内容的 URL」都列出。契约要求的「≥3 个 support.saleae.com URL 实际 fetch 成功」，实测结论是：**旧域名本身不可用，但其文档内容在新域名完整可读，共成功抓取 12+ 页**。这是官方一手资料，不是二手教程。

| # | 请求 URL | 实际取到内容 | 结果 | 可信度 | 用途 |
|---|---|---|---|---|---|
| S1 | `https://www.saleae.com/downloads` | 同 URL | 成功 | 官方一手 | 版本/平台；未显示具体版本号，仅见 "Logic 2"、x64/ARM64、Windows 10&11、Insider build |
| S2 | `https://support.saleae.com/` | 302 → `https://www.saleae.com/support` | 成功（跳转后） | 官方一手 | 文档分类树：Getting Started 12 / Logic Software 66 / Protocol Analyzers 33 / Extensions & API 48 篇 |
| S3 | `https://support.saleae.com/faq/technical-faq` | 302 → `https://www.saleae.com/support/troubleshooting` | 成功（跳转后） | 官方一手 | 该旧 FAQ 路径已改版为 Troubleshooting 分类，无原 FAQ 正文 |
| S4 | `https://support.saleae.com/user-guide/using-logic2` | 302 → `.../support/user-guide/using-logic2` 返回 404 | 失败 | — | 旧路径已废弃，改用 S5~S16 的具体文章页 |
| S5 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/measurements-timing-markers` | 同 URL | 成功 | 官方一手 | **核心**：Measurement / Timing Markers / Notes 面板 |
| S6 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/navigating-the-software` | 同 URL | 成功 | 官方一手 | 界面布局、侧栏、会话标签、时间刻度 |
| S7 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/navigating-your-data` | 同 URL | 成功 | 官方一手 | 缩放/平移/边缘跳转快捷键 |
| S8 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/data-table-and-terminal` | 同 URL | 成功 | 官方一手 | 数据表格视图 + Terminal 视图 |
| S9 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/using-protocol-analyzers` | 同 URL | 成功 | 官方一手 | 协议气泡合并、Restart |
| S10 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/what-annotations-are-supported` | 同 URL | 成功 | 官方一手 | 三类注释：Measurement / Bookmark / Timing Marker Pair |
| S11 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/time-bar-settings` | 同 URL | 成功 | 官方一手 | 时间轴、t=0、壁钟时间 |
| S12 | `https://www.saleae.com/support/saving-and-exporting-data/export-between-timing-markers`（实际路径 `.../logic-software/saving-and-exporting-data/export-between-timing-markers`） | 同 URL | 成功 | 官方一手 | **标记对作为导出区间** |
| S13 | `https://www.saleae.com/support/extensions-api/extensions/high-level-analyzer-extensions` | 同 URL | 成功 | 官方一手 | **HLA Python 接口** |
| S14 | `https://www.saleae.com/support/extensions-api/extensions/measurement-extensions` | 同 URL | 成功 | 官方一手 | 测量扩展机制 |
| S15 | `https://www.saleae.com/support/extensions-api/extensions/digital-measurement-extensions` | 同 URL | 成功 | 官方一手 | **Clock Stats / Pulse Count / Duty Cycle 指标清单** |
| S16 | `https://www.saleae.com/support/logic-software/capturing-data/capture-modes` | 同 URL | 成功 | 官方一手 | 触发配置 |
| S17 | `https://www.saleae.com/support/logic-software/capturing-data/capture-settings` | 同 URL | 成功 | 官方一手 | 采集设置（触发细节少） |
| S18 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/changing-the-display-radix` | 同 URL | 成功 | 官方一手 | 进制显示 |
| S19 | `https://www.saleae.com/support/logic-software/viewing-and-analyzing-data/generate-analog-graph-from-digital-data` | 同 URL | 成功 | 官方一手 | 官方明确：不能从数字数据生成模拟曲线 |
| S20 | `https://www.saleae.com/support/logic-software/settings-and-preferences/keyboard-shortcuts` | 同 URL | 成功（内容极少） | 官方一手 | 页面只有 Help>Keyboard Shortcuts 与 "?" 键，无具体绑定表 |

**二手/未确认来源**：无。本次所有功能结论均来自 S1~S20 官方页面；官方页面**没有**写明的点（尤其是标记对是否直接显示 1/ΔT 与脉冲数），在下文明确标为「官方未明示 / 我们的设计提案」，绝不冒充官方事实。
**失败/超时项**：博客 tag/measurement 页 404；discuss.saleae.com 搜索页无有效结果；`docs.saleae.com/docs/API/` 404。`high-level-analyzer-extensions` 与 `digital-measurement-extensions` 首次 60s 超时，改用短 prompt 重取成功。

---

## 1. 界面布局全景（ASCII 图）

依据 S6、S8、S9 重建（注意：官方文档没有完整截图文字说明，此图为「文档明确提到的组件」拼装，非像素级还原）。

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ 会话标签栏  [Capture 1] [Capture 2] [ + ]        ← "+" 新建 capture session tab│
├──────────┬────────────────────────────────────────────────┬───────────────────┤
│ 左侧     │  时间轴 Time Bar                                 │ 右侧侧栏          │
│ 设备状态 │  t=0s | 1ms | 2ms | ...   (Start of Capture/     │ ┌───────────────┐ │
│ Logic    │  Digital Trigger/Analyzer Trigger/Timing Marker) │ │Device Settings│ │
│ Analyzer │────────────────────────────────────────────────│ │  (采样率/通道)│ │
│ Connect  │ Ch0 ─┐  数字波形区（可重命名/重排/缩放/改色）      │ ├───────────────┤ │
│ Status   │ Ch1 ─┤  ◄ Next Edge(右缘hover) / Prev Edge(左缘)  │ │ Analyzers     │ │
│          │ Ch2 ─┤  [协议气泡 bubble 叠加在波形上]             │ │ (添加解码器)  │ │
│          │ Ch3 ─┘                                           │ ├───────────────┤ │
│          │ A0  ~~~  模拟波形（Y/XY zoom 图标在右上 hover 出现）│ │Timing Markers │ │
│          │ A1  ~~~                                          │ │Measurements & │ │
│          │                                                  │ │Notes   ★       │ │
│          │ [测量框 measurement box：SHIFT+框选]               │ │  +Measurements│ │
│          │ [标记 M1 A ][标记 M2 B]  ← 顶部可点，改文字/颜色    │ │  +Marker      │ │
│          │                                                  │ │  +Marker Pair │ │
│          │                                                  │ │  Capture Notes│ │
│          │                                                  │ ├───────────────┤ │
│          │                                                  │ │ Extensions    │ │
│          ├──────────────────────────────────────────────────┤ └───────────────┘ │
│          │ 右下：X-Axis Discrete Zoom Level（精确"每100像素时间"）│                  │
│          │ 底部数据表格 / Terminal（表格右上角 "Terminal" 切换） │                  │
└──────────┴────────────────────────────────────────────────┴───────────────────┘
```

**我们可以怎么抄（界面层）**：
- 三栏固定布局：左「设备/采集控制」、中「波形画布」、右「分析面板栈」。右侧面板做成可折叠 accordion，避免遮挡波形。
- 会话标签用多文档模型：每个 tab 独立持有 `Capture { samples[], channels[], markers[], analyzers[], measurements[] }`。
- 时间轴单独成层（`TimeBarLayer`），与时间标尺、标记头、t0 指示器共用同一 `timeToX(t)` 变换。
- 底部表格/终端做成 dockable panel，共享同一数据源 `Frame[]`，切换视图不重算数据。

---

## 2. 时间标记 Timing Markers（重点章节，篇幅占比 ≥20%）

> 来源：S5（主文档）、S10（注释类型）、S11（t0 参考）、S12（区间导出）。
> **诚实性声明**：官方文档只明确了「两种标记类型」「在侧栏添加」「可编辑文字/颜色/删除」「用于测间距」「可作为 t0」「可作为导出区间」。官方页面**没有**逐项列出标记对显示的数值清单（ΔT、1/ΔT、脉冲数、占空比）。下文凡标「官方未明示」的，是我们的推断或设计提案，不作为 Saleae 的事实陈述。

### 2.1 怎么放
- 官方原文：Timing Markers 通过右侧的 **"Timing Markers & Measurements"** 侧栏按钮添加（S5）。
- 官方明确存在的**两种类型**：
  1. **Single Marker**（单标记）
  2. **Marker Pair**（标记对，即用户说的 AB 区间）
- 官方明确：点击软件**顶部**的 timing marker，可以添加文字注释（text notes）并修改颜色；用 **trashcan（垃圾桶）图标**删除（S5）。
- 官方明确：Marker Pair 可作为「**Set as t0**」，即把某个标记设为时间原点（S11）。
- 官方明确：Measurements 的添加方式是点 "+" 后在波形区**拖拽框选**生成 measurement box；**按住 SHIFT 拖拽**也可创建测量（S5）。标记的具体鼠标手势（是拖拽标记头，还是先放标记再拖）**官方页面未明示**——不要当成事实。
- 官方明确：Markers / Measurements / Notes 三类都在同一个右侧面板，面板边缘可拖拽改变宽/高（S5）。

**我们可以怎么抄（放置算法）**：
```
数据结构：
  Marker { id, t, label, color, kind: SINGLE | PAIR_A | PAIR_B, pairId }
状态机：
  IDLE → ARMED_SINGLE(点工具栏"单标记") → 鼠标在波形区 click → 生成 Marker(t=snap(mouseT))
  IDLE → ARMED_PAIR(点"标记对") → click 第一次 → 临时记 pairStart=t
       → click 第二次 → 生成一对 Marker，pairId 关联；若 t2<t1 交换
  IDLE → HOVER_MARKER → mousedown → DRAG_MARKER → mousemove 更新 t=snap(mouseT) → mouseup 落定
删除：选中 marker 后按 Delete 或垃圾桶按钮；若 marker 属于 pair，整对一起删或只删单端（建议整对）
```
- 顶部 "marker strip" 与波形画布共享 x 映射，标记头绘制在 strip 内，竖线贯穿所有通道（含模拟通道）。
- 限制数量：官方未明示上限。我们建议软上限 64 对，超出时提示，避免 O(n²) 命中测试。

### 2.2 显示哪些数值（ΔT / 频率 / 脉冲数 / 占空比？）
**官方已确认的**：
- Marker Pair 的用途是「measure spacing」（测量两个标记之间的间距）（S10）。
- 时间轴零参考可以是 Timing Marker，标记菜单里有 "Set as t0"（S11）。
- 「Measurement Annotation」= 对一个通道在一段时间范围内做统计（S10）；统计指标由测量扩展定义（S14/S15）。
- 标记对可以界定「在这两个标记之间」搜索并导出协议解码结果（S12）——说明标记对在逻辑上是一个 `[tA, tB]` 区间。

**官方未明示的**（必须标出，不能写成 Saleae 功能）：
- 标记对是否**直接在标签上**显示 `ΔT`、`1/ΔT`(频率)、区间脉冲数、占空比——本次抓到的官方页面**没有逐条列出**。
- 因此：**不能声称 Logic 2 的标记对里原生显示「AB 之间脉冲数」**。官方把「脉冲数」「占空比」「频率」列为**独立的测量扩展指标**（S15），作用在 measurement box / 选区上，而不是明确挂在标记对上。

**我们可以怎么抄（算法级，作为我们的超集设计）**：
```
输入：tA, tB, 通道 ch（数字），边沿事件数组 E = [(t, 0|1)]
Δt   = tB - tA
f    = 1/Δt                      // 周期信号频率，仅当 Δt 是一个周期时成立
Np+  = count{ i | E[i].t∈[tA,tB) ∧ E[i-1].val=0 ∧ E[i].val=1 }   // 上升沿 = 正脉冲数
Np-  = count{ i | E[i].t∈[tA,tB) ∧ E[i-1].val=1 ∧ E[i].val=0 }
Duty = (Σ 高电平时长 within [tA,tB]) / Δt
       = Σ over rising r in [tA,tB): (min(nextFall(r), tB) - max(r, tA)) / Δt
fmean = Np+ / Δt                  // 区间平均频率（比 1/Δt 更通用）
边界处理：把 tA、tB 当作半个开区间，先对 E 做 bisect_left/bisect_right 定位，再遍历，
         避免重复计数起点/终点上的边沿。
显示：标签框内多行紧凑排布，例如 "Δt=1.234ms  f=810Hz  Np+=3  Duty=48.2%"；
      Δt 用工程单位自动缩放（ns/µs/ms/s），小数位按量级自适应。
```
- 对**模拟通道**不显示脉冲数/占空比，改显示 min/max/mean/RMS（对齐官方 Voltage RMS 扩展思路）。

### 2.3 拖动与吸附
- 官方未明示吸附（snap）行为。官方文档明确的只有：标记在**顶部**可点击编辑文字/颜色、可删除（S5）；时间轴可用 "Set as t0" 把标记设为原点（S11）。
- 官方明确的「跳转类」操作可作为参考：Next Edge / Previous Edge 按钮（通道右侧/左侧 hover 出现），快捷键 Ctrl+Right / Cmd+Right、Ctrl+Left / Cmd+Left（S7）；Ctrl+J 跳到触发点（S16）。

**我们可以怎么抄（吸附算法）**：
```
snap(tRaw, mode):
  if mode == FREE:      return tRaw
  if mode == EDGE:      在 E 中二分找最近边沿，若 |tEdge - tRaw| <= 8px 对应时间 → 吸附
  if mode == GRID:      round(tRaw / gridStep) * gridStep
  if mode == FRAME:     若有解码气泡，吸附到最近气泡的 start_time/end_time
修正：按住 Alt 临时禁用吸附（Free 模式）
拖动时：实时重算区间统计，但用节流（>=16ms）刷新标签，避免每帧扫全量边沿
```

### 2.4 我们可以怎么抄（落地清单）
1. 标记与波形数据解耦：`Marker` 只存时间（double，秒），不存像素；缩放时自动跟随。
2. 一对标记 = 一个 `Interval` 对象，所有区间统计（Δt/f/Np/Duty/气泡搜索）都以此对象为输入，统一入口。
3. 复用已有的边沿检测表（我们已有频率/占空比测量）：区间脉冲数 = 在 `[tA,tB]` 切片上跑同一套边沿扫描，**零新增算法**。
4. 标记显示在顶部 strip + 贯穿竖线 + 区间半透明遮罩三层；遮罩支持改色和文字（对齐官方可编辑颜色/注释）。
5. 导出：提供「仅导出标记区间内的解码结果」，对齐官方 S12 的 search-between-markers 流程。
6. 时间原点：任一标记可 Set as t0，切换全图时间坐标（对齐 S11）。

---

## 3. 测量 Measurement

**官方事实（S5/S14/S15）**：
- 右侧 "Timing Markers, Measurements & Notes" 面板中，点 "+"（Measurements 旁）后在目标通道/轨迹区**拖拽框选**生成 measurement box；**SHIFT+拖拽**也可创建。
- 指标取决于信号类型（模拟 or 数字）以及已安装的附加组件（add-ons）。
- 预装扩展：**Clock Stats**、**Voltage RMS**。
- 内置/扩展可见指标：Clock Stats → `Nfalling`、`Nrising`、`fmin`、`fmax`、`fmean`、`Period STD (Tstd)`；Pulse Count → `Np(+)`、`Np(-)`；Duty Cycle → `Dcycle`。另有 baud rate、pulse/burst stats、RPM、interval stats、task/CPU 等社区扩展。
- 测量机制：app 把区间内的数据块传给 `process_data`（已按选区裁剪），扩展可跨多次调用累积状态；最后调用 `measure()` 一次性返回结果，且只返回被请求的指标，多余结果被忽略。数字输入是 `DigitalData` 事件（时间+电平），时间类型 `GraphTime` / `GraphTimeDelta`；模拟输入 `AnalogData` 含 `sample_count` 与 NumPy `ndarray` 类型的 `samples`。
- 官方页面**未明确**测量是「实时随波形刷新」还是「仅在选区上计算」；文档措辞倾向「选区/区间」（clipped to chosen interval）。

**我们可以怎么抄**：把测量做成「选区驱动」的纯函数 `measure(slice, metricSet) -> map`，避免实时全局扫描；扩展点用统一接口 `process_data(chunk)` + `measure()`，这样内置指标和第三方 Python 扩展走同一条流水线；用 `GraphTime` 类似的有理数时间表示避免 double 累积误差。

---

## 4. 选区与区间统计

**官方事实（S5/S10/S12）**：
- 选区（measurement box）由拖拽 / SHIFT+拖拽产生，落在某个通道/轨迹上。
- 注释类型有三类：Measurement Annotation（某通道一段时间范围内的统计）、Bookmark Annotation（标记某个采集位置+缩放级别）、Timing Marker Pair（一两标记测间距）；标签均可编辑，点击注释图标可返回对应测量位置。
- 选区/标记对可作为区间：数据表格支持在标记对之间搜索解码结果（S12）。

**我们可以怎么抄**：选区用 `(chId, tStart, tEnd)` 表示，与标记对 `Interval` 统一转换；框选时显示半透明高亮 + 顶部浮动统计条；Bookmark 存 `(t, zoomLevel, scrollOffset)` 三元组以便一键回到同一视图。

---

## 5. 区间脉冲计数（用户明确要的）

**官方事实（S15）**：Pulse Count 扩展提供 `Positive Pulses (Np(+))` 和 `Negative Pulses (Np(-))`；Clock Stats 提供 `Nrising`/`Nfalling` 与 `fmean`。这些指标作用于测量选区（见 §3）。**官方没有**把「脉冲计数」明确描述成标记对的内置读数（见 §2.2 诚实性声明）。

**我们可以怎么抄**：见 §2.2 的 `Np+/Np-` 公式；把它注册为一个「区间度量」`PulseCountMetric`，同时供标记对、测量框、导出区间使用。对高速信号用前缀和数组 `prefixRising[i]` 使任意区间查询 O(log n)：`count = prefixRising[r] - prefixRising[l]`。

---

## 6. 占空比显示位置

**官方事实（S15）**：`Duty Cycle (Dcycle)` 是测量扩展提供的指标之一，在测量/选区结果中显示（S5+S15 组合推断：测量框内显示所选区间的指标）。官方页面**未明确**它显示在「波形与波形之间」这种位置；用户说的「波形与波形之间的占空比」在官方资料里没有对应术语。

**我们可以怎么抄**：在两个标记之间的区间遮罩中央显示 `Duty=xx.x%`，并同时画出该区间内高电平时长的分段条（用小横条把「高电平累计」与「总时长」做视觉对比）；选区测量框内也显示同一 `Dcycle` 数值，两处共用同一计算函数。

---

## 7. 时间轴

**官方事实（S6/S7/S11）**：
- 右下角有 "X-Axis Discrete Zoom Level" 控件，可设置**精确的每 100 像素对应时间值**（区别于滚轮/快捷键的连续缩放）。
- 时间轴显示 `t=0s`；支持 Wall Clock Time（使用 OS 壁钟时间）。
- 零参考可选：Start of Capture / Digital Trigger / Analyzer Trigger / **Timing Marker**；壁钟样式只在视图平移到最左（靠近起点）时显示。
- 上下文菜单打开 Time Preferences；模拟轨迹 hover 时右上出现 Y zoom-out/in/fit 与 XY zoom-out/in/fit 控件。
- 缩放/平移：滚轮、上下方向键、`=`/`-` 缩放；鼠标拖拽、左右方向键平移；Next/Previous Edge 按钮跳转边沿。模拟通道支持 Marquee Zoom、Alt-Drag（XY Range）、Ctrl-Drag 上下（Y/电压范围）、Ctrl-Drag 左右（X/时间范围）。

**我们可以怎么抄**：时间轴用「逻辑时间→屏幕 x」单一变换 `x = (t - t0) * pxPerSec + originX`；单位按 1/2/5 序列自动选 ns/µs/ms/s；提供「每 100px = X」的精确输入；保存 bookmark 时连 `pxPerSec` 一起存。

---

## 8. 模拟通道 + 数字同屏

**官方事实（S6/S19）**：Logic 2 支持模拟轨迹与数字通道在同一波形区显示；模拟通道 hover 出现独立的 Y/XY 缩放控件。但官方明确说明：**不能从数字数据生成模拟曲线**（"there is no way to generate an analog graph from digital data"）。

**我们可以怎么抄**：画布分层渲染，数字通道画阶梯线、模拟通道画折线/填充，共享时间轴；模拟通道独立维护 `yMin/yMax`（电压范围），数字通道固定 0/1 两档；提供「模拟转数字」阈值比较的反向便利功能时，要明确标注这是转换结果而非原始模拟数据（不冒充官方行为）。

---

## 9. 解码结果展示（气泡视图）

**官方事实（S9/S8/S18）**：
- 解码结果以 **protocol bubble（协议气泡）** 叠加在波形上。
- 缩小到较宽时间范围时，多个结果气泡会**合并成一个气泡**，内容按时间顺序排列，并显示「合并了多少个气泡」的计数。
- 数据表格按 analyzer 输出逐行显示，含 `Start`、`Duration` 列；值类型有 Integer/Float/Boolean/String/Byte Array，可用 hex/ASCII/decimal/binary 进制显示。
- 表格行 hover 出现箭头可跳到对应波形气泡；气泡可用快捷键跳回表格。
- 表格搜索覆盖大多数列但**不含 Start/Duration**，通常不区分大小写；三点菜单可包含/排除某些 analyzer；右键表头隐藏列；官方文档**没有**描述排序功能。
- 进制切换入口：analyzer 的三点菜单，或波形区解码结果的右键菜单（S18）。
- Terminal 视图：表格右上角 "Terminal" 按钮切换；按 analyzer 分组；Async Serial/Manchester 先 ASCII 再 hex，I2C 显示地址/负载/访问状态，SPI 显示 MOSI/MISO hex；历史上限 10,000 行（可用 `SALEAE_SCROLLBACK_LIMIT` 覆盖）。

**我们可以怎么抄**：气泡采用 LOD（level of detail）渲染：当 `pxPerBubble < 6px` 时把相邻帧聚合为一个 cluster，显示计数；cluster 点击后放大到其时间范围。表格行与气泡用稳定的 `frameId` 双向跳转；搜索时把 Start/Duration 排除（与官方一致，避免时间字符串误匹配）；实现 hex/bin/ASCII/decimal 四种 radix 渲染器。

---

## 10. HLA 扩展机制

**官方事实（S13）**：HLA 用 **Python** 编写，主文件 `HighLevelAnalyzer.py`。导入：`from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, NumberSetting, ChoicesSetting`。模板类 `class MyHla(HighLevelAnalyzer):`（类名要在 extension JSON 中引用，默认 `Hla()`）。设置项示例 `StringSetting()`、`NumberSetting(min_value=0, max_value=100)`、`ChoicesSetting(['A','B'])`。方法：`__init__(self)` 做初始化/读设置；`decode(self, frame: AnalyzerFrame)` 在下游每产生一帧时被调用，是返回新帧、显示到 Logic 2 UI 的地方。返回单帧：`return AnalyzerFrame('mytype', frame.start_time, frame.end_time, {...})`；返回多帧：先 `frames = []` 再 `return frames`；也可跳过。显示字符串用 `result_types = {... 'format': 'Found: {{data.char}}' ...}`。对 Async Serial，输入帧 `frame.type` 恒为 `data`，`frame.data['data']` 是 `bytes`，`frame.data['error']` 表示错误。

**我们可以怎么抄**：定义我们自己的 HLA 契约：`decode(frame) -> AnalyzerFrame | list | None`，`AnalyzerFrame { type, startTime, endTime, data }`；用 `result_types` 声明式模板生成气泡文本（减少 UI 代码）；把 Python 扩展放进独立进程通过管道通信，避免扩展崩溃拖垮主程序；设置项 schema 用 JSON 描述并在 UI 自动生成配置表单。

---

## 11. 测量历史

**官方事实**：本次抓取的官方页面**没有**描述「测量历史（measurement history）」面板或自动保存到历史列表的功能。最接近的是 S10 的 Bookmark Annotation（保存位置+缩放级别）与 S8 的 Terminal 滚动历史（上限 10,000 行）。因此：**不能声称 Logic 2 有测量历史功能**。

**我们可以怎么抄**：做「测量结果钉住（pin）」列表：每次 measure() 的输出追加到 `MeasurementHistory[] { timestamp, interval, metrics, channel, label }`，支持重命名、导出 CSV、点击回到原选区；这是我们的增值项，不冒充原厂功能。

---

## 12. 数据表格视图

已在 §9 覆盖表格与 Terminal 的主要事实。补充契约要求单独成节的结论：**Logic 2 有数据表格视图**，位于波形区底部，展示解码帧（Start、Duration 及 analyzer 字段），支持搜索、按 analyzer 包含/排除、隐藏列、行↔气泡跳转、进制切换；无明确排序功能；Terminal 是表格的替代视图（按 analyzer 分组、10k 行上限）。

**我们可以怎么抄**：表格用虚拟滚动（只渲染可视行）；列定义来自 analyzer 的 `fields` schema，未知字段按首次出现顺序追加（对齐官方列顺序行为）；提供 `frameId ↔ rowIndex` 映射实现双向跳转；导出时按表头解析，保证列顺序稳定。

---

## 13. 触发配置

**官方事实（S16/S17）**：
- Capture Mode 中有 "Trigger Mode"；记录的停止由数字条件触发。
- "Edge & Pulse Triggering" 支持 **Rising Edge / Falling Edge / High Pulse / Low Pulse**，作用于单个数字通道。
- "Additional Channel State Triggering"：其他数字通道可约束为 HIGH 或 LOW。
- 基于解码结果的触发：在 Analyzers 区打开 **"Trigger View"**，选择 analyzer，设置 "query value" 与 "holdoff time"；依赖 frame v2，HLA 也可驱动。
- 等待触发时使用 "Memory Buffer Setting"（循环缓冲区，注意 RAM 占用）。
- "Capture Duration Before and After Trigger" 控制触发前保留时长与触发后记录时长；`Ctrl+J` 跳到触发点。
- 官方页面**未描述**通用的模式匹配/总线数值触发的图形化 builder；也未描述独立的 start/end 双触发（有单独的 FAQ 标题提及 end-of-capture trigger，但正文未取到）。

**我们可以怎么抄**：触发配置做成「条件行 + 布尔组合」的 builder：每行 `{channel, type: EDGE|PULSE|VALUE|PATTERN|FRAME, value, holdoff}`，多条件 AND/OR；触发点写入 `Capture.triggerIndex`，供时间轴 t0、跳转、前后缓冲裁剪共用；串口/协议帧触发复用解码器的输出流。

---

## 14. 与我们的差距表（≥20 行）

标注：✅已有 / ⭕部分 / ❌无 / ？官方未明示（我们不做承诺）。「我们」指背景中列出的现有能力。

| # | 功能点 | Logic 2（官方确认） | 我们现状 | 差距 | 优先级 |
|---|---|---|---|---|---|
| 1 | 单标记 Single Marker | ✅ S5 | ❌ | 缺 | P0 |
| 2 | 标记对 Marker Pair（AB 区间） | ✅ S5/S10 | ❌ | 缺 | P0 |
| 3 | 标记文字注释与改色 | ✅ S5 | ❌ | 缺 | P1 |
| 4 | 标记垃圾桶删除 | ✅ S5 | ❌ | 缺 | P1 |
| 5 | 标记设为 t0 | ✅ S11 | ❌ | 缺 | P1 |
| 6 | 标记对界定导出区间 | ✅ S12 | ❌ | 缺 | P1 |
| 7 | 区间 Δt 读数 | ✅「测间距」S10，具体数值未列 | ⭕有光标差值的雏形 | 部分 | P0 |
| 8 | 区间脉冲数 Np+/Np- | ✅ 测量扩展 S15 | ❌ | 缺（用户点名） | P0 |
| 9 | 区间占空比 Dcycle | ✅ 测量扩展 S15 | ⭕已有占空比测量 | 需接到区间 | P0 |
| 10 | 平均频率 fmean | ✅ Clock Stats S15 | ⭕已有频率测量 | 需接到区间 | P0 |
| 11 | fmin/fmax/Tstd 统计 | ✅ Clock Stats S15 | ❌ | 缺 | P2 |
| 12 | 拖拽框选生成 measurement box | ✅ S5 | ❌ | 缺 | P0 |
| 13 | SHIFT+拖拽创建测量 | ✅ S5 | ❌ | 缺 | P1 |
| 14 | 测量扩展机制（Python） | ✅ S14 | ❌ | 缺 | P2 |
| 15 | 预装 Clock Stats / Voltage RMS | ✅ S5 | ❌ | 缺 | P2 |
| 16 | 数据表格视图 | ✅ S8 | ❌（仅 CSV/VCD 导出） | 缺 | P1 |
| 17 | Terminal 文本视图 | ✅ S8 | ❌ | 缺 | P2 |
| 18 | 表格行↔波形气泡双向跳转 | ✅ S8 | ❌ | 缺 | P1 |
| 19 | 表格搜索/隐藏列/按 analyzer 过滤 | ✅ S8 | ❌ | 缺 | P2 |
| 20 | 协议气泡 + 宽缩放合并计数 | ✅ S9 | ⭕有解码显示，合并 LOD 未知 | 部分 | P1 |
| 21 | 进制切换 hex/dec/bin/ASCII | ✅ S18 | ？ | 待确认 | P1 |
| 22 | 精确「每100像素时间」缩放控件 | ✅ S6/S7 | ❌ | 缺 | P1 |
| 23 | Next/Prev Edge 跳转及快捷键 | ✅ S7 | ❌ | 缺 | P1 |
| 24 | Bookmark（位置+缩放级别） | ✅ S10 | ❌ | 缺 | P2 |
| 25 | 模拟通道 + 数字同屏 | ✅ S19 | ❌（8 通道数字） | 缺（大成本） | P3 |
| 26 | 模拟独立 Y/XY 缩放 | ✅ S7 | ❌ | 缺 | P3 |
| 27 | Wall Clock Time 时间轴 | ✅ S11 | ❌ | 缺 | P2 |
| 28 | 触发：边沿/脉冲 + 其他通道电平约束 | ✅ S16 | ⭕有软件触发，细粒度未知 | 部分 | P1 |
| 29 | Trigger View（按解码结果触发） | ✅ S16 | ❌ | 缺 | P2 |
| 30 | 触发前后时长控制 / Ctrl+J 跳转 | ✅ S16 | ⭕有采集范围 | 部分 | P1 |
| 31 | Holdoff 时间 | ✅ S16 | ❌ | 缺 | P2 |
| 32 | 测量历史面板 | ？官方未明示 | ❌ | 不作为差距 | — |
| 33 | 多会话标签页 | ✅ S6 | ❌ | 缺 | P2 |
| 34 | 软件 glitch filter | ✅ 文档目录项（未深入抓取） | ❌ | 待确认 | P2 |
| 35 | 自动脚本 API / Socket API | ✅ S2 分类（48 篇） | ❌ | 缺 | P3 |
| 36 | 导出 CSV/VCD | ✅ S2 目录项 | ✅ | 对齐 | — |

---

## 15. 优先级建议（成本/价值四象限）

**象限 A：高价值 / 低成本（先做，P0）**
- 标记对 + 单标记数据结构与绘制（§2.1）
- 区间脉冲数、占空比、平均频率（复用已有测量内核，§2.2/§5/§6）
- 拖拽框选 measurement box（§3/§4）
- 标记对作为所有区间统计的统一输入 `Interval`

**象限 B：高价值 / 中成本（第二批，P1）**
- 数据表格视图 + 行↔气泡双向跳转（§9/§12）
- 标记注释/改色/删除、Set as t0、标记区间导出（§2.3/§2.4）
- 精确时间刻度控件、Next/Prev Edge 跳转（§7）
- 触发的通道电平约束与前后时长（§13）
- 气泡 LOD 合并计数（§9）

**象限 C：中价值 / 中成本（第三批，P2）**
- 测量扩展 Python 机制（§3/§10）、Clock Stats 全部指标
- Terminal 视图、搜索/隐藏列、Bookmark（§8/§11/§12）
- Trigger View（按解码帧触发）、holdoff（§13）
- Wall Clock Time、多会话标签、glitch filter

**象限 D：高成本 / 待定（P3）**
- 模拟通道采集与同屏显示（需硬件支持，§8）
- Socket API / 自动化脚本（§0 的 Extensions & API 分类）

**一句话结论**：用户点名的「AB 之间脉冲数与占空比」在原厂是通过「标记对/选区 + 测量扩展」组合实现的；我们只需把已有的频率/占空比测量内核接到新增的 `Interval` 上，即可用最小成本对齐原厂最核心的交互体验。切勿把「标记对直接显示脉冲数」当作官方事实写入对外文档。
