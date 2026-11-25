# PulseView 功能调研

> 目标：不是产品宣传，而是把 PulseView 的 GUI 拆成「界面长什么样 / 怎么交互 / 数据结构是什么」，供我们上位机照抄。
> 方法：只使用官方文档实测抓到的内容；文档没写的标「文档未提及」，不猜。

## 0. 资料来源

实际 fetch 成功（URL + 用途）：

| URL | 用途 | 关键产出 |
|---|---|---|
| `https://sigrok.org/wiki/PulseView` | 主页面 | 定位（Qt logic analyzer/oscope/MSO GUI）、三句 Features：O(log N) 渲染、协议解码、Trace groups；截图含 I2C 解码与 2 路模拟通道 |
| `https://sigrok.org/wiki/Protocol_decoders` | 解码器生态 | 数量 **131**，分类桶为 "Supported protocol decoders" / "Possible candidates for future protocol decoders" |
| `https://sigrok.org/doc/pulseview/0.4.2/manual.html` | **主手册**（最有价值），分 8 段抓取 | §2 Overview、§4 采集、§5 数据分析、§5.1 光标标记、§5.2 专用解码器、§5.3 多视图/会话、§6 解码器、§7-8 导入导出 |
| `https://sigrok.org/wiki/Input_output_formats` | 格式清单 | 输入 13 种、输出 12 种，srzip 即 .sr |

fetch 失败/404（如实记录，不据此编造）：

- `https://sigrok.org/wiki/Features` → 404。改用 PulseView 主页面 Features 段 + manual 代替。
- `https://sigrok.org/wiki/PulseView_GUI_concepts` → 404（主页面链接指向它，但实测 404）。
- `https://sigrok.org/wiki/Protocol_decoders_List` → 404。
- `https://sigrok.org/wiki/Faq` → 404。
- 手册全文一次性抓取两次超时，改为按章节分 8 段抓取后成功。

证据强度说明：手册 0.4.2 是较老版本，但交互描述（光标、标记、多视图、会话）是最权威的一手材料；标注「文档未提及」的点表示这 0.4.2 手册与该 wiki 页面没写，不代表新版一定没有。

---

## 1. 界面布局全景

手册 §2 只给出「以波形为中心」的描述，没画分区图；下图是按手册中出现的控件名（New View 按钮在最左、时间标尺、信号标签区、解码行、Zoom-to-Fit、Open/Save 带下拉箭头）综合还原的布局，每区名称用官方就叫法。

```
+------------------------------------------------------------------------------+
| 菜单栏  [File] [Edit] [View] [Decoders] [Settings] [Help]        (文档未逐项列出) |
+------------------------------------------------------------------------------+
| 工具栏 ←最左 [New View] | Open▾ | Save▾ | 采集控制 | Zoom in/out | Zoom-to-Fit | 光标按钮 |
+-------------------------------------------+----------------------------------+
| 信号标签区 (signal label area)             | 波形视图 (view)                  |
|  D0 ─── name ── [颜色块]  ←可拖动右边界    | 时间标尺 time scale              |
|  D1 ─── name ──                            | ─┬─ 蓝色旗标(cursors)            |
|  D2 ─── name ──                            | 数字/模拟波形                    |
|  ───────────────┐                          | 解码行 decode signal (三角/标签) |
|                 │←拖动改标签区宽           | 蓝色虚线 = 触发处 marker         |
+-------------------------------------------+----------------------------------+
| (可选) 第 2 个 View：点击 New View 新建，可重排                                |
+------------------------------------------------------------------------------+
| 状态栏：文档未提及                                                            |
+------------------------------------------------------------------------------+
```

分区与交互（逐区）：

- **顶部工具栏**：手册明确点名的按钮/控件：`New View`（"on the very left of the toolbar"）、`Zoom in/out`、`Zoom-to-Fit`、`Open` 的小箭头（选输入格式）、`Save` 的小箭头（导出菜单）、光标按钮（"clicking on the cursor button"）。
- **信号标签区**："position the mouse cursor at the right edge of the label area (or left edge of the viewing area)" → "Your mouse cursor will change shape and you now can drag the border"，用来给信号长名字而不挤占波形区（§5.3.1）。
- **主画布**：缩放靠 "zoom in/zoom out buttons"、"scroll wheel of your mouse"、"pinch/expand gestures on your touch panel"（§5）。
- **解码行**：右键解码信号区域（"not on the signal label on the left"）弹出导出菜单（§6.7）；点行箭头/标签进 per-row 设置（§6.4）。
- **时间标尺**：双击建 marker，右键出上下文菜单（§5.1）。
- **底部状态栏**：**文档未提及**。

**我们可以怎么抄（布局）**：
1. 固定三段式布局：`Toolbar(top)` / `LabelPane(left, 可拖右边界)` / `WaveCanvas(center, 可多实例)`。
2. 每个 View 是独立对象 `{id, type: digital|analog|decode, ds:同一个session, xRange:{t0,t1}}`，多个 View 共享一个 session，但各自保存滚动/缩放状态。
3. LabelPane 宽度 `labelW` 作为 session 元数据持久化；鼠标落在 `labelW±3px` 时光标改 `SizeHor` 并进入 drag-resize。
4. 工具栏每个按钮的一个 action 对应一个 `QUndoCommand`，便于后续做撤销（PulseView 是否支持 undo：文档未提及）。

---

## 2. 时间轴（timeline）

### 2.1 外观
手册 §5 称其为 "Time scale (used to set up and show markers)"，它就是顶部一条带刻度的时间标尺；标尺区域里有两个"蓝色旗标"代表光标边界，触发产生的 marker 是"vertical dashed blue line"。

### 2.2 缩放行为
- 按钮 `Zoom in/out`、鼠标滚轮、触摸板 pinch/expand 三种方式（§5 原文）。
- `Zoom-to-Fit`：把全部采集数据塞进所有 view；采集过程中保持激活："the Zoom-to-Fit button stays active if you click it"，自动 fit 直到采集完成或再点一次取消；设置里可开 "Always Zoom-to-Fit"。
- 中键拖拽 / 滚动条：**文档未提及**（我们不能据此说有或没有）。

### 2.3 单位与刻度密度
手册 0.4.2 **未提及** ns/µs/ms/s 自动切换规则、1/2/5 取整、防重叠阈值。这是文档空白点，下面 2.4 给的是**我们的实现方案**，不冒充 PulseView 行为。

### 2.4 我们可以怎么抄（时间轴，算法级）
目标：给定可视区间 `[t0,t1]` 和画布像素宽 `W`，画刻度与标签。

```
step_raw = (t1-t0) / targetTicks        # targetTicks ≈ W/120 px
p = floor(log10(step_raw)); m = step_raw/10^p
step = (m<1.5?1 : m<3.5?2 : m<7.5?5 : 10) * 10^p   # 1/2/5*10^n 取整
unit = 选 ns/µs/ms/s 使主标签数值落在 [1,1000)      # 仅显示单位前缀切换
for k in ceil(t0/step) .. floor(t1/step):
    x = (k*step - t0)/(t1-t0)*W
    if k%5==0: 长刻度+标签; else if 相邻像素>=8: 短刻度; else 跳过
```
- 防重叠：相邻`x`间距 `< 60px` 时标签只画每 2/5/10 个；`< 4px` 时只画长刻度。
- 标签文字用 `fmt(k*step, unit)`，尾部标注单位（如 `50µs`）；单位切换只换前缀与除数值，不改变 step 计算。
- 缩放时 `t0,t1` 以鼠标所在时间点为锚点：新 `t0' = tm - (tm-t0)*factor`，`t1' = tm + (t1-tm)*factor`，`tm = t0 + mx/W*(t1-t0)`。

---

## 3. 时间光标 / AB 标记

### 3.1 外观
手册 §5.1：启用后时间标尺上出现两个"蓝色旗标"（blue flags），中间区域显示时间距离；触发产生的 marker 是蓝色虚线、不可移动。

### 3.2 交互
- 开关：`clicking on the cursor button` 启用光标。
- 移动边界：`move both of its boundaries around by clicking on the blue flags in the time scale area`。
- 整体拖动：`move both boundaries at the same time by dragging said label`（拖两旗之间的标签）。
- 快速放置：`press 1 and 2 on your keyboard to attach either side to your mouse cursor`；`They will stay put when you either press Esc or click with the left mouse button`。即按 1 把 A 边吸附到鼠标、按 2 把 B 边吸附到鼠标，Esc/左键落定。
- 数量：**一对（两个边界 A/B）**，文档未提及更多对。

### 3.3 显示内容
- 两边界之间 "shows the time distance, its inverse (i.e. the frequency) and/or the number of samples encompassed"。
- 空间不足时：`hover the mouse cursor over the label in the middle` 或 `right-click on the label to configure what you want to see`（可配置显示项）。

### 3.4 我们可以怎么抄（光标，算法级）
数据结构：`cursor = {enabled:bool, tA:double, tB:double, fields:["ΔT","f","N"]}`。
1. 画两条竖线于 `x(tA),x(tB)`，旗标画在标尺区可点区域 `y∈[0,rulerH]`。
2. 命中测试：`|mx-x(tA)|<6` 进入拖 A，`|mx-x(tB)|<6` 拖 B，`x(tA)<mx<x(tB)` 拖整段。
3. 键盘 1/2：进入 `attach` 态，`tA = pixelToTime(mx)` 实时更新；Esc/左键 commit（`Esc` 恢复 commit 前的值，左键保留当前）。
4. ΔT = `tB-tA`；f = `1/(tB-tA)`（ΔT>0）；N = `round((tB-tA)*sampleRate)`。
5. 中间标签宽度 `labelW = xB-xA`；`<120px` 只显示主字段，hover 显示 tooltip 完整值，右键菜单切换 fields。

---

## 4. 区间选择与测量

PulseView 的"区间"实际由**光标对**（§3）充当：两旗之间就是选中区间，显示 ΔT/f/采样数（§5.1）；专用解码器 Counter/Timing 在区间上做统计（§5.2）。独立的"框选矩形 region"操作：**文档未提及**。

**我们可以怎么抄**：用现成 cursor 对做区间，避免再造一套；选区渲染为半透明矩形 `fillRect(xA,0,xB-xA,H)`；区间内统计走统一函数 `analyzeRange(ch, tA, tB)`，输出 `{edges, pulses, period, freq, duty}` 供 §5/§6 复用。若要做独立框选，左键拖出 region，松手后把 `[tA,tB]` 喂给同一函数。

---

## 5. 脉冲计数

手册 §5.2 "Special-Purpose Decoders" 原文列出（这些"analyzes the data instead of decoding it"）：

- **Counter** — "counts pulses and/or groups of pulses (i.e. words)"，即脉冲数或脉冲组（字）数。
- **Guess bitrate** — "guesses the bitrate when using a serial protocol"。
- **Jitter** — "determines the jitter (variance) of a signal"。
- **Timing** — "shows the time passing between the chosen signal edges"（选中边沿之间的时间）。

添加步骤、结果具体呈现位置：§5.2 **未提及**（只说这类工具分析数据而非解码）。§6 通用解码器添加流程可复用（见 §9）。

**我们可以怎么抄（脉冲计数）**：
```
countPulses(ch,tA,tB,edge='rising',minWidth=0):
  edges = [t for t in ch.transitions if tA<=t<=tB and type==edge]
  pulses = 0; groups=0; inGroup=false
  for i in 0..len(edges)-2:
      w = edges[i+1]-edges[i]
      if w>=minWidth: pulses++ ; inGroup=true
      else if inGroup: groups++; inGroup=false
  if inGroup: groups++
  return {pulses, groups}
```
UI 呈现：作为一条 decode-like 行，行内标签 `Counter: 128 pulses / 16 words`；点击行高亮对应通道；参数（edge 极性、minWidth、group gap）放在右侧属性面板。

---

## 6. 频率/周期/占空比

- 手册 §5.1：频率是**光标区间的派生量**——"its inverse (i.e. the frequency)"，即 ΔT 的倒数，属于**按区间计算**，不是全程实时逐周期刷新。
- §5.2 **Timing** 工具："shows the time passing between the chosen signal edges"，即选中边沿间时间 → 周期。
- 专门的"频率计/占空比实时测量"控件：**文档未提及**（我们已有的每通道频率/占空比侧栏比手册描述更细；不要反过来标成 PulseView 有而我们没有）。

**我们可以怎么抄**：
```
measure(ch,tA,tB):
  e = transitions(ch,tA,tB)
  periods = [e[i+2]-e[i] for i in range(0,len(e)-2,2)]   # 完整周期
  f = 1/mean(periods); T = mean(periods)
  high = sum(highDuration(e[i],e[i+1])) for i in even indices
  duty = high / (tB-tA)
```
显示挂在光标中间标签（ΔT/f）与测量侧栏两处；数据一律由区间工具函数算，避免 UI 与解码器口径不一致。

---

## 7. 游标吸附（snap）

手册 §5.1 提到按 `1`/`2` 把光标边"attach ... to your mouse cursor"并"stay put on Esc/left click"，但**没有写是否吸附到信号边沿**；§5/§5.1 全文未出现 snap 一词。结论：**文档未提及吸附到边沿**（不能说有）。

**我们可以怎么抄**（作为我们可加的增强，不声称 PulseView 有）：
```
snapTime(t, chans, pxPerSec, radiusPx=8):
  dt = radiusPx/pxPerSec
  candidates = [e for ch in chans for e in ch.transitions if abs(e-t)<dt]
  return min(candidates, key=lambda e:abs(e-t)) if candidates else t
```
吸附开关做成工具栏 toggle；拖动光标时 `t = snapTime(rawT)`，按住 Alt 临时禁用吸附，便于精确放置。

---

## 8. 多视图

手册 §5.3.2：`You can create multiple views by clicking on the "New View" button on the very left of the toolbar`；`These can be rearranged as you wish`。主页面 Features 有 "Trace groups support"；截图说明含 "PulseView + scope" 的 2 路模拟通道；§6.3 讲 "Using Decoders on Analog Signals"（把模拟转逻辑再解码）。视图类型的明确枚举、删除视图步骤：**文档未提及**。

**我们可以怎么抄**：
- 多视图数据模型：`views: [{id, kind, channelRefs, t0, t1}]`，`channelRefs` 引用同一 session 的通道，避免复制采样数据。
- New View 点击 → `views.push({id:nextId(), kind:'digital', t0:0, t1:duration, channelRefs:[]})`，并在布局里插一个新 `WaveCanvas`。
- "重排"用 dock widget 的 ` dockWidgetArea` 或自绘 splitter 顺序；每个 view 独立保存 `t0,t1`，但共享全局光标（ab）与 marker 列表——这是联动关键。
- 模拟+数字同屏：同一 session 的通道有 `type: analog|digital`，view 只决定渲染器（模拟画折线、数字画方波），解码器通道由 `channelRefs` 跨类型引用。

---

## 9. 解码联动

手册 §6.1：加解码器 "by clicking on ➊ and selecting I²C from the list adds a new decode signal to the view"；PulseView 自动把已有信号匹配到解码器所需信号（"SCL and SDA have been automatically assigned"），用默认参数即解码；结果 "displays these annotations as part of the decode signal"。
§6.4：点行箭头或标签 → 可 show/hide 整行或选择 annotation classes（如关掉 SPI 的 bit annotations，保留 warning/error）。
§6.2 Decoder Stacking：可把更高层解码器叠加在已有解码结果上。
§6.7：右键解码信号区域（注意"not on the signal label"）→ 导出菜单，最后一项仅在光标启用时可用；格式串可在 Decoders 菜单设置里编辑，例 `%s %d: %1`。
"点解码行波形会跳到对应时间/高亮"这一类联动：**文档未提及**（手册只写点行箭头/标签做设置，不写点 annotation 定位波形）。

**我们可以怎么抄**：
- 解码行数据：`decodeRow = {id, decoder, inputs:{role:channelId}, params:{}, annotations:[{tStart,tEnd,class,text}], visibleClasses:Set}`。
- 行用独立委托绘制在时间轴上，每个 annotation 画成标签块；我们已有的"标三角"继续保留，但补 annotation 块以承载文字。
- 点击行头 → 右侧属性面板绑定该 `decodeRow`，改 params 触发 `reDecode()`（增量：只重算可视区间）。
- 若加联动：点 annotation → `setCursorRange(a.tStart,a.tEnd)` 并把 view 滚动到该时间；这属于我们的增强。

---

## 10. 书签/标记（bookmark / marker）

手册 §5.1 明确有 **markers**：
- 创建：`just double-click on it and it'll create one for you where your mouse cursor is at the time`（在时间标尺上双击）；或 `use the context menu when right-clicking on the ruler or a signal trace`。
- 重命名/移动：`click on its label ... change its name, or drag it to reposition it`。
- 时间差：`the time difference between the markers` 通过 `hovering over one of them` 显示；`This works on the cursor, too`。
- 触发产生的特殊 marker：`It cannot be moved and appears as a vertical dashed blue line`。
- "bookmark" 一词：**文档未提及**（功能对应物是 marker）。

**我们可以怎么抄**：
```
marker = {id, t, name, kind:'user'|'trigger', color}
// 时间标尺 hit-test：双击 -> markers.push({t:pixelToTime(mx),name:nextName(),kind:'user'})
// 右键标尺/波形 -> 菜单 [Add marker here, ...]；同理 push
// 拖动：|mx-x(m.t)|<6 -> 更新 m.t；点击标签 -> inline QLineEdit 改名
// hover：显示最近 marker 的 Δt = m.t - cursor.tA（或相邻 marker 差）
```
数据存 session 元数据，随 .sr/.pvs 保存（见 §12）。

---

## 11. 全局导航条（overview）

手册 §7-8 与全文抓取结果：`Overview` 只是手册章节标题；**没有**描述全局导航条/波形缩略图/overview widget。结论：**文档未提及**（不能说 PulseView 有）。

**我们可以怎么抄**（作为我们可加的增强，不声称 PulseView 有）：
- 在主画布底部加 24px 高 overview：`drawDecimated(samples, width=overviewW, maxPoints=overviewW*2)`（用 min/max 包络降采样，保留跳变）。
- 画视口矩形 `[t0,t1]` 映射到 overview 的 x 区间；拖动矩形平移，拖两端缩放。
- overview 数据源与主波形同一份 sample buffer，不另存采样；主视图每次 `t0/t1` 变化只重绘视口框。

---

## 12. 会话保存/加载（.sr 文件）

手册 §5.3.3 原文：
- 关闭时 `it automatically saves the sessions you currently have open, including the signal configuration and any protocol decoders you might have added`；下次启动 `restored to its previous state`。
- `.sr` 文件："This metadata is also saved with every .sr file you save so that the next time you open the .sr file, your signal configurations, views and decoders are restored"。
- 独立 setup 文件："These metadata files have the ending `.pvs` (PulseView Setup) and can be edited in any text editor"；`save/load buttons` 可随时保存/加载。
- 格式页：`srzip` = "The current (v2) sigrok session file format (*.sr)"。

**我们可以怎么抄**：
- 会话拆两层：`raw samples`（二进制/压缩块）+ `metadata`（JSON，对应 .pvs）。
- metadata 结构建议：`{version, channels:[{id,name,type,color,enabled}], views:[{...}], decoders:[...], cursors:{tA,tB,fields}, markers:[...], samplerate, triggeredAt}`。
- 保存：打包 `zip`：samples.bin + metadata.json（对齐 srzip 思路），扩展名自定；加载：先读 metadata 还原 UI，再懒加载 samples。
- 自动恢复：退出写 `last_session.json`，启动检测并提示恢复；提供 `-c/--clean` 式开关跳过恢复（手册 §8 有 `pulseview -c`，"Don't restore previous sessions on startup"）。

---

## 13. 优先级建议（实现成本 × 用户价值 四象限）

| 象限 | 功能 | 一句话理由 |
|---|---|---|
| 低成本 / 高价值（先做） | §3 时间光标 AB + ΔT/f/N | 手册确认存在，复用现有拖拽/左键体系即可，直接补最大痛点 |
| 低成本 / 高价值 | §4 区间选择与测量统一入口 | 把已有侧栏测量接入光标区间，口径统一、改动小 |
| 低成本 / 高价值 | §10 marker 双击/右键创建、改名 | 标尺上十几行代码，价值高 |
| 低成本 / 高价值 | §12 会话保存/加载（含自动恢复） | 复用已有导出，加 metadata 即可 |
| 低成本 / 中价值 | §2 时间轴 1/2/5 取整 + 防重叠 | 纯绘制算法，显著提升可读性 |
| 中成本 / 高价值 | §5 Counter/Timing/G/Jitter 专用工具 | 手册点名的 4 个分析工具，作为解码行复用现有框架 |
| 中成本 / 高价值 | §6 区间频率/周期/占空比 | 与 §4 共用分析函数，按区间算更准 |
| 中成本 / 中价值 | §9 解码行属性面板 + annotation classes 显隐 | 手册明确有 per-row 设置，能减少视觉噪声 |
| 中成本 / 中价值 | §8 多视图（New View） | 需改布局与数据引用，但共享 session 可行 |
| 高成本 / 中价值 | §7 边沿吸附 | 需全局边沿索引，属增强，非文档要求 |
| 高成本 / 中价值 | §11 overview 导航条 | 需降采样与视口联动，文档未提及，排在最后 |

---

## 14. 与我们现有实现的差距表

| # | 功能 | PulseView 有 | 我们有 | 差距 |
|---|---|---|---|---|
| 1 | 时间轴刻度自适应（1/2/5） | 文档未提及具体算法，但有 time scale | 滚轮缩放，刻度算法未说明 | 明确算法与防重叠 |
| 2 | 时间单位 ns/µs/ms/s 切换 | 文档未提及 | 未提及 | 空白，需自建 |
| 3 | Zoom-to-Fit 按钮 + Always Zoom-to-Fit | 有（§5） | 未提及 | 缺 |
| 4 | 键盘 1/2 快速放光标、Esc/左键落定 | 有（§5.1） | 左键光标（单次） | 缺 AB 快速放置 |
| 5 | AB 光标对 + ΔT/f/采样数标签 | 有（§5.1） | 左键光标（单点） | 缺成对区间 |
| 6 | 光标标签 hover/右键切换显示字段 | 有（§5.1） | 未提及 | 缺 |
| 7 | Marker 双击创建/改名/拖动 | 有（§5.1） | 未提及 | 缺 |
| 8 | Marker 间时间差 hover | 有（§5.1） | 未提及 | 缺 |
| 9 | 触发蓝色虚线 marker（不可动） | 有（§5.1） | 软件触发（边沿/电平/脉宽/模式） | 缺触发位置可视化 |
| 10 | 独立框选 region | 文档未提及 | 未提及 | 空白，可不做 |
| 11 | Counter 脉冲计数（含 words） | 有（§5.2） | 测量侧栏有边沿数，无区间 Counter 工具 | 缺专用工具 |
| 12 | Guess bitrate | 有（§5.2） | 未提及 | 缺 |
| 13 | Jitter（variance） | 有（§5.2） | 未提及 | 缺 |
| 14 | Timing（选中边沿间时间） | 有（§5.2） | 脉宽测量（侧栏） | 缺按选中边沿的区间工具 |
| 15 | 频率按区间算（ΔT 倒数） | 有（§5.1） | 每通道实时频率 | 口径不同，补区间方式 |
| 16 | 占空比专用测量 | 文档未提及 | 每通道占空比 | 我们反而更细，保持 |
| 17 | 吸附到边沿 | 文档未提及 | 未提及 | 空白，增强项 |
| 18 | 多视图 New View + 重排 | 有（§5.3.2） | 单视图 8 通道 | 缺 |
| 19 | Trace groups | 有（主页面 Features） | 未提及 | 缺 |
| 20 | 模拟波形视图 + 模拟转逻辑解码 | 有（§6.3/截图） | 仅数字 | 缺（若硬件支持） |
| 21 | 解码结果行显隐 / annotation classes 过滤 | 有（§6.4） | 表格+三角，无过滤 | 缺 |
| 22 | 解码器堆叠（stacking） | 有（§6.2） | UART/I2C/SPI/CAN 平铺 | 缺 |
| 23 | 解码注释导出（格式串可编辑） | 有（§6.7） | CSV/VCD/二进制 | 缺注释导出 |
| 24 | 标签区宽度可拖动 | 有（§5.3.1） | 未提及 | 缺 |
| 25 | .sr 会话含配置/视图/解码器 | 有（§5.3.3） | 仅导出数据，无会话 | 缺 |
| 26 | .pvs 可编辑 setup 文件 | 有（§5.3.3） | 无 | 缺 |
| 27 | 关闭自动保存/启动恢复/-c 跳过 | 有（§5.3.3/§8） | 无 | 缺 |
| 28 | 全局导航条/缩略图 | 文档未提及 | 未提及 | 空白，增强项 |

> 注：标「文档未提及」的行是**我们也不能声称 PulseView 有**的空白点，列在表里便于区分「真差距」与「双方都没有」。

---

## 自检清单（本报告）

- **12 个必查点结论**：①时间轴=部分（有 time scale，算法文档未提及）；②AB 光标=有（1/2/Esc/左键，ΔT/f/N）；③区间选择=由光标对承担，独立框选未提及；④脉冲计数=有（Counter）；⑤频率/周期=有（区间倒数 + Timing）；⑥占空比=文档未提及（我们更细）；⑦吸附=文档未提及；⑧多视图=有（New View）；⑨解码联动=部分（行设置明确，点 annotation 定位未提及）；⑩marker=有；⑪overview=文档未提及；⑫会话=有（.sr/.pvs）。
- **URL fetch**：成功 URL 4 个（PulseView、Protocol_decoders、manual、Input_output_formats），manual 分 8 段；失败 404 四个已如实记录；总成功 fetch 调用 10+ 次。
- **「我们可以怎么抄」小节**：§1、§2.4、§3.4、§4、§5、§6、§7、§8、§9、§10、§11、§12 共 12 处 ≥ 8。
- **差距表行数**：28 行 ≥ 15。
- **空话检查**：每条均带具体控件名/交互/算法/出处，无「支持很多功能」类表述。
