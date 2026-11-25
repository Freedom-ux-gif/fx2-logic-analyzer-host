# 时间线 / AB 区间 / 区间统计 —— 设计方案

> 文档性质：纯设计，不含实际代码。所有代码块均为伪代码/算法骨架，供实现者直接照写。
> 适用对象：`13_web/static/app.js`（单体 IIFE）与 `13_web/static/index.html`。
> 权威现状：`Waveform` 已处理 devicePixelRatio，`bandH = H/8` 占满画布，`draw()` 6 步顺序，状态栏 5 个 `span`。以下设计均以这些现状为基线。

## 0. 设计目标与非目标

### 0.1 用户原始诉求
- "不知道时间概念" → 需要**时间线**：画布上直接看到"现在看到的是哪一时刻、每格多少时间"。
- "标定 AB 之间脉冲数、AB 之间的时间" → 需要**AB 区间标记**：两个可拖动端点 + 区间读数。
- "占空比啥的数据" → 需要**区间统计**：按通道给出脉冲数、占空比、频率、脉宽等。

### 0.2 目标
1. 不改变 8 通道均分的整体观感，在画布底部新增一条时间轴。
2. 提供 A/B 两点放置、拖动、清除的完整交互，并实时显示 ΔT、频率、样本数。
3. 在 AB 区间内按通道计算统计量，与现有"全量测量"并列常驻显示。
4. 所有新增状态挂到现有 `Waveform`/`App` 对象，不引入模块、依赖或框架。

### 0.3 非目标（明确不做）
- 不做多组 AB 标记（只保留一组 A/B）。
- 不做时间轴拖拽平移/拖动刻度改视图（缩放平移沿用现有手势）。
- 不做统计结果的导出/复制按钮（后端 API 已存在，导出属后续需求）。
- 不改后端 `/api/measure`；区间统计前端本地算，后端保持原样。
- 不改现有解码事件逻辑与 `EVENT_COLORS`。

### 0.4 设计原则（贯穿全文）
- **单一数据源**：标记存样本索引，视图存 `start/span`，时间由 `rate` 换算。三者只在一处换算，避免多个真值。
- **整数样本**：A/B 吸附整数，所有统计以整数样本为边界。
- **前端优先**：数据已在内存，交互读数必须同步（无网络往返）；后端仅作兜底。

---

## 1. 时间线

### 1.1 布局改造

**现状**：`bandH = H / 8`，8 个通道从 y=0 铺到 y=H，无轴区。

**改造方案**：
- 轴高 `AXIS_H = 28`（px）。理由：11px 等宽字体标签高度约 11px，上下各留 ~8px padding 后 28px 刚好容纳标签与次刻度短线，且不明显挤压波形（对 H=400 的画布，通道仅压缩 7%）。
- `bandH` 重算：`bandH = (H - AXIS_H) / 8`。波形区高度从 H 变为 `H - AXIS_H`。
- 左侧 `LABEL_W` 区域底部**留空**：时间轴只在 `x >= LABEL_W` 的绘图区绘制；`x < LABEL_W` 且 `y >= axisY0` 的矩形填 panel 背景色，可画一个小号 "t" 作为轴标识。理由：通道标签列与时间刻度语义不同，混排会造成误读；留空也保证 `xToSample` 的映射域不被破坏。
- 竖向网格线只画到 `axisY0`，不进入轴区（轴区有自己的刻度线）。

**改后坐标公式**（设 `plotX0 = LABEL_W`, `plotW = W - LABEL_W`, `AXIS_H = 28`, `axisY0 = H - AXIS_H`）：

| 量 | 公式 | 说明 |
|---|---|---|
| 通道带高 | `bandH = (H - AXIS_H)/8` | 8 通道均分绘图区 |
| 通道 i 中线 | `cy_i = bandH * i + bandH/2` | i=0..7 |
| 样本→x | `sampleToX(s) = plotX0 + (s - start)/span * plotW` | 与现有一致 |
| x→样本 | `xToSample(x) = start + (x - plotX0)/plotW * span` | 与现有一致 |
| 轴顶 y | `axisY0 = H - AXIS_H` | 轴区 [axisY0, H) |
| 轴底线 y | `axisBaseY = H - 4` | 标签基线留 4px |

> 实现注意：若现有 `sampleToX/xToSample` 已内建 `LABEL_W` 偏移，则上式直接复用；若未内建，须在这两个函数里统一加上 `plotX0`，否则波形与轴会错位 66px。**这是集成时的第一个校验点**。

### 1.2 刻度算法（含伪代码）

**输入**：`spanSec = span / rate`、`plotW`。
**目标**：每 80~120px 一个主刻度标签。取目标间隔 `TARGET_PX = 100`，则主刻度数 `n ≈ plotW / 100`，原始步长 `raw = spanSec / n`。
**取整**：用 1/2/5×10ⁿ 序列（工程上最易读的"整数步长"）。

```
// 返回 >= raw 的最小 "1/2/5×10^n" 值
function niceStep(raw):
    if raw <= 0: return 1e-9
    n = floor(log10(raw))
    pow = 10^n
    frac = raw / pow            // 落在 [1, 10)
    if   frac <= 1: m = 1
    elif frac <= 2: m = 2
    elif frac <= 5: m = 5
    else:           m = 10      // 10*pow 即 1*10^(n+1)
    return m * pow

function buildTicks(startSample, span, rate, plotW):
    spanSec = span / rate
    nTarget = max(1, round(plotW / 100))   // 100px 一个主标签
    raw     = spanSec / nTarget
    stepSec = niceStep(raw)

    // 降级处理
    if stepSec < 1e-9: stepSec = 1e-9       // <1ns 无物理意义，钳到 1ns
    if stepSec > 1000: stepSec = 1000       // >1000s 钳到 1000s 并提示"跨度过大"

    stepSamples = stepSec * rate            // 步长转成样本数（可能非整数，无妨）
    minorSec    = stepSec / 5               // 每主刻度间 4 条次刻度

    // 主刻度：从采集起点 0 开始，取 >= 视图左端时间 的第一个整步长
    t0 = startSample / rate                 // 视图左端的绝对时间
    kFirst = ceil((t0 - 1e-12) / stepSec)   // -1e-12 抗浮点误差
    majors = []
    for k = kFirst; ; k++:
        t = k * stepSec
        if t > t0 + spanSec + 1e-12: break
        majors.push({ t: t, x: plotX0 + (t*rate - startSample)/span*plotW })
        if majors.length > 1000: break      // 防御性上限

    // 次刻度：每相邻主刻度间插 4 条
    minors = []
    for each pair (m_i, m_i+1) in majors:
        for j = 1..4:
            t = m_i.t + j*minorSec
            if t >= m_i+1.t: continue
            minors.push({ x: plotX0 + (t*rate - startSample)/span*plotW })
    return { majors, minors, stepSec }
```

**降级说明**：
- `stepSec < 1ns`：量化噪声无意义，钳到 1ns；若此时主刻度数仍 >200，跳过标签只画次刻度。
- `stepSec > 1000s`：钳到 1000s；跨度极大时画布上可能只有 1~2 条刻度，属于可接受降级。

**主 vs 次画法**：
- 主刻度：`ctx.moveTo(x, axisY0); lineTo(x, H-4)` 实线，`strokeStyle = --grid`；下方写标签。
- 次刻度：`ctx.moveTo(x, H-10); lineTo(x, H-4)` 短线（6px），颜色 `--grid` 降透明度 0.5，无标签。理由：主次分层能在不堆标签的前提下表达 finer 的时间密度。

### 1.3 标签防重叠

- 标签文本 `txt = fmtTimeWithUnit(t)`（见 1.4），等宽字体 `11px var(--mono)`。
- 宽度估算：`w = txt.length * 11 * 0.6`（≈6.6px/字符）。理由：等宽字体字宽约 0.6×字号，误差 <5%。
- 相邻主刻度像素距离 `d = x[i+1] - x[i]`；安全间距 `safe = (w[i] + w[i+1])/2 + 8`。
- **跳过规则**：若 `d < safe`，隔一个保留一个——遍历 majors，维护 `lastKeptX` 与 `lastKeptW`；当候选标签的 `x - lastKeptX < (lastKeptW + w)/2 + 8` 时跳过该标签（但刻度线仍画）。这样最坏情况下标签密度减半，保证任意两个可见标签不重叠。
- **边界裁剪**：
  - 最左：若 `x - w/2 < plotX0`，改为左对齐绘制 `x = plotX0 + 2`（textAlign='left'）。
  - 最右：若 `x + w/2 > W`，改为右对齐 `x = W - 2`（textAlign='right'）。
  - 中间：居中 `textAlign='center'`。
  - 理由：不裁剪会丢失首/末刻度语义；对齐到边界比丢弃标签信息更完整。

### 1.4 单位规则

以**绝对时间** `t`（秒）选择单位并格式化（与现有 `fmtTime(sec)` 口径一致，但此处强制带单位后缀）：

| 阈值 | 单位 | 缩放系数 | 小数位 | 示例 |
|---|---|---|---|---|
| `t < 1e-6` | ns | ×1e9 | 0 | `250 ns` |
| `1e-6 ≤ t < 1e-3` | µs | ×1e6 | 1 | `12.5 µs` |
| `1e-3 ≤ t < 1` | ms | ×1e3 | 2 | `1.25 ms` |
| `t ≥ 1` | s | ×1 | 3 | `2.500 s` |

> 原点处 `t=0` 显示 `0 s`（统一用 s，避免 "0 ns" 的怪异）。理由：阈值与人类读示波器的习惯一致（µs 级看数字信号），小数位控制在 4 位有效数字内，标签宽度可预测（≤9 字符）。

### 1.5 时间原点

**建议：从采集起点算 0（绝对时间），不从视图左端算。**

理由：
1. 用户抱怨"没有时间概念"，本质是缺少跨视图稳定的参照系；采集起点是物理上唯一的 t=0，缩放/滚动时同一时刻的标签值不变。
2. 若从视图左端算 0，每次平移标签全变，用户无法把两次观察对应起来，反而加重困惑。
3. AB 区间的 ΔT 与时间轴共用同一原点，ΔT 可直接与轴读数对照（B 读数 − A 读数 = ΔT）。
代价：数值可能较大（如 48e6 样本 @100MS/s = 0.48s），但 1.4 的量级表已覆盖到 s，无问题。

### 1.6 绘制骨架（伪代码）

```
function drawTimeline(ctx, start, span, rate, plotW, W, H, majors, minors):
    AXIS_H = 28; axisY0 = H - AXIS_H; baseY = H - 4
    ctx.save()
    // 1) 轴区背景
    ctx.fillStyle = cssVar('--panel')
    ctx.fillRect(LABEL_W, axisY0, plotW, AXIS_H)
    ctx.fillStyle = cssVar('--panel')          // 左侧标签列底部留空
    ctx.fillRect(0, axisY0, LABEL_W, AXIS_H)

    // 2) 轴线（上边界 + 基线）
    ctx.strokeStyle = cssVar('--grid'); ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(LABEL_W, axisY0+0.5); ctx.lineTo(W, axisY0+0.5)
    ctx.moveTo(LABEL_W, baseY+0.5);  ctx.lineTo(W, baseY+0.5)
    ctx.stroke()

    // 3) 次刻度（短线）
    ctx.strokeStyle = gridWithAlpha(0.5)
    ctx.beginPath()
    for tk in minors:
        if tk.x < LABEL_W or tk.x > W: continue
        ctx.moveTo(round(tk.x)+0.5, H-10); ctx.lineTo(round(tk.x)+0.5, baseY)
    ctx.stroke()

    // 4) 主刻度 + 标签（含防重叠）
    ctx.strokeStyle = cssVar('--grid'); ctx.beginPath()
    for tk in majors:
        if tk.x < LABEL_W or tk.x > W: continue
        ctx.moveTo(round(tk.x)+0.5, axisY0); ctx.lineTo(round(tk.x)+0.5, baseY)
    ctx.stroke()

    ctx.font = '11px ' + cssVar('--mono')
    ctx.fillStyle = cssVar('--text-dim')
    lastX = -1e9; lastW = 0
    for tk in majors:
        txt = fmtTimeWithUnit(tk.t); w = txt.length * 6.6
        // 防重叠
        if tk.x - lastX < (lastW + w)/2 + 8: continue
        lastX = tk.x; lastW = w
        // 边界裁剪
        if tk.x - w/2 < LABEL_W:      ctx.textAlign='left';   px = LABEL_W + 2
        elif tk.x + w/2 > W:          ctx.textAlign='right';  px = W - 2
        else:                         ctx.textAlign='center'; px = tk.x
        ctx.fillText(txt, px, H - 9)
    // 5) 轴标识
    ctx.textAlign='center'; ctx.fillStyle = cssVar('--text-dim')
    ctx.fillText('t', LABEL_W/2, H - 9)
    ctx.restore()
```

---

## 2. AB 区间标记

### 2.1 数据结构

```
Waveform.markers = {
    a: null,        // 样本索引（整数）
    b: null,        // 样本索引（整数）
    active: false   // 是否处于 AB 放置模式
}
```

**a/b 用整数并吸附到样本**：`a = Math.round(xToSample(x))`。理由：
- 现有全部读数（cursor 值、measure API 的 window、脉宽样本数）都以整数样本为单位，混用小数会让"区间含 N 个样本"出现 N 或 N+1 的歧义。
- 缩放后鼠标落点常落在两个样本之间，吸附保证任意缩放级别下 A/B 都指向确定的样本，`ΔT = (b-a)/rate` 可精确复现。
- 吸附误差 ≤ 半个样本（@100MS/s 为 5ns），远小于人眼操作精度，可接受。

不变量（实现时断言）：`a !== null ⇒ a ∈ [0, n-1]`；`b !== null ⇒ b ∈ [0, n-1]`；展示时令 `lo=min(a,b), hi=max(a,b)`，允许反向放置后自动交换。

### 2.2 交互设计（完整鼠标事件状态机）

**进入/退出放置模式**：
- 工具栏新增按钮 `#btn-mark-ab`，点击切换 `markers.active`（按下态高亮）；
- 快捷键 `M` 同样切换（理由：频繁测量时不必移动鼠标到工具栏）。
- `active=true` 时左键单击不再设置 `cursor`，专用于放 A/B；`active=false` 时恢复原行为。

**状态枚举**：`mode ∈ { CURSOR, PLACE_A, PLACE_B, DRAG_A, DRAG_B }`
- `CURSOR`：默认，左键 = 放光标。
- `PLACE_A`：`active=true` 且 `a===null`，下一次左键放 A，随后自动转 `PLACE_B`。
- `PLACE_B`：`active=true` 且 `a!==null && b===null`，下一次左键放 B，随后转 `CURSOR`（但 `active` 保持 true 以便拖动）。
- `DRAG_A/DRAG_B`：mousedown 命中已有标记线（±4px）时进入，mousemove 拖动，mouseup 退出。

```
// 命中测试：返回 'a' | 'b' | null
function hitMarker(x):
    xa = sampleToX(markers.a); xb = sampleToX(markers.b)
    if markers.a!=null and |x-xa| <= 4: return 'a'
    if markers.b!=null and |x-xb| <= 4: return 'b'
    return null

onMousedown(e):
    x = e.offsetX
    hit = hitMarker(x)
    if hit:  mode = (hit=='a') ? DRAG_A : DRAG_B; return
    if not markers.active:
        Waveform.cursor = clamp(round(xToSample(x)), 0, n-1); return   // 原行为
    if markers.a == null:
        markers.a = clamp(round(xToSample(x)),0,n-1)
        markers.b = null; mode = PLACE_B
    elif markers.b == null:
        markers.b = clamp(round(xToSample(x)),0,n-1)
        if markers.b == markers.a: markers.b = null; return            // 拒绝零宽
        mode = CURSOR
    else:
        // 已有完整区间，再次左键：重开新区间（A 移到此处）
        markers.a = clamp(round(xToSample(x)),0,n-1); markers.b = null
        mode = PLACE_B

onMousemove(e):
    x = e.offsetX
    if mode == DRAG_A:
        markers.a = clamp(round(xToSample(x)),0,n-1)
        if markers.a > markers.b: swap(markers.a, markers.b)   // 保持 a<=b
    elif mode == DRAG_B:
        markers.b = clamp(round(xToSample(x)),0,n-1)
        if markers.b < markers.a: swap(markers.a, markers.b)
    // 拖动时实时重算区间统计（节流：rAF 合并）

onMouseup(e):
    if mode in {DRAG_A, DRAG_B}: mode = CURSOR
    // 触发一次区间统计刷新

onDblClick(e):   clearMarkers()      // 双击清空 A/B
onContextMenu(e):
    hit = hitMarker(e.offsetX)
    if hit: e.preventDefault(); clearMarkers()   // 右键标记线清空
```

- `clearMarkers()`：`a=b=null; mode=CURSOR`；是否退出放置模式由 UI 决定（建议保持 `active` 不变，便于连续测量）。
- 冲突消解核心：**放置模式下屏蔽光标设置**，拖动优先于放置（先做命中测试）。

### 2.3 视觉设计

| 元素 | 颜色/线型 | 理由 |
|---|---|---|
| A 线 | `#3fb950` 绿色实线，宽 1.5px | 与红色光标 `#ff7b72`、解码三角色区分 |
| B 线 | `#d29922` 黄色实线，宽 1.5px | 与 A 区分，暖色系配对 |
| 区间背景 | `rgba(63,185,80,0.08)` 填充 lo..hi 整高 | 8% 透明度不遮挡波形细节 |
| 顶部区间条 | 轴区内 `axisY0+2` 处，高 4px，绿色圆角 | 像视频编辑器选区，一眼看到区间跨度 |
| A/B 标签 | 轴区上方小矩形底色 `#3fb950`/`#d29922`，白字 11px | 画在轴区（不覆盖波形），避免遮挡 |

- 标签位置：`x = sampleToX(a/b)`，`y = axisY0 - 14`（在轴区上沿之上、通道带最底部），若 x 靠边则同 1.3 做左右对齐裁剪。
- 标记线贯穿 `y=0..axisY0`（跨全部通道），在波形之后绘制以置于顶层；解码三角被压时标记线仍可见（线细，不遮挡三角主体）。
- 区间条两端画小竖耳（4px 高）强化端点感。

### 2.4 数值显示（用户核心需求）

**三项读数**：
- `ΔT = (hi - lo) / rate` 秒（用 `fmtTime` 带单位）。
- `频率 = rate / (hi - lo)` Hz（ΔT 为 0 时显示 `—`）。
- `样本数 = hi - lo` 个（整数，`fmtNum` 千分位）。

**显示位置建议：画布浮动标签 + 状态栏双显**。
- 画布浮动标签：画在区间条中点上方（`x = (xa+xb)/2, y = axisY0 - 14`），文本 `ΔT=12.5µs · 80.0kHz · 1250 smp`，半透明深色底。理由：读数贴着区间，视线不用来回跳。
- 状态栏新增 `<span id="stat-range">区间: —</span>`：常驻显示同样三项（无区间时 `区间: —`）。理由：状态栏固定位置便于阅读/截图，且画布标签可能被滚动出界。
- 不放在侧栏：侧栏留给逐通道统计表（见 3.4），语义分层更清晰。

---

## 3. 区间统计（"脉冲数""占空比"）

### 3.1 统计项清单（逐通道，0..7）

对每个可见通道输出：
1. 上升沿数 `risings`：样本由 0→1 的次数。
2. 下降沿数 `fallings`：样本由 1→0 的次数。
3. 高电平样本数 `highCount`、低电平样本数 `lowCount`（`high+low = len`）。
4. 占空比 `duty = highCount / len`（0~1）。
5. 边沿总数 `edges = risings + fallings`。
6. 高脉宽 min/max/avg（样本数，末尾未闭合段不计入 avg 的"完整周期"口径见 3.3）。
7. 低脉宽 min/max/avg（样本数）。
8. 频率 `freq = cycles / (len/rate)`，其中 `cycles` 为完整周期数（见 3.3）。

### 3.2 算法（可运行级伪代码）

**输入**：`data`(Uint8Array), `lo`, `hi`(整数样本，半开区间 [lo,hi)), `channel`(0..7), `rate`。
**输出**：统计对象。
**向量化友好性**：整段只需**一次线性扫描**；循环内不含数组分配、不含闭包、位运算读位；min/max/累加全是标量。4800 万样本在现代 V8 中单次循环约 80~150ms，满足 <200ms。

```
function statRange(data, lo, hi, channel, rate):
    len = hi - lo
    out = { risings:0, fallings:0, highCount:0, lowCount:0, duty:0,
            edges:0, cycles:0, hiMin:Infinity, hiMax:0, hiSum:0,
            loMin:Infinity, loMax:0, loSum:0,
            hiRun:0, loRun:0, freq:0, minPulse:0, maxPulse:0, avgPulse:0 }
    if len <= 0: return out                       // 空区间
    mask = 1 << channel
    prev = (data[lo] & mask) ? 1 : 0
    // 首段游程初始化
    if prev: out.hiRun = 1; out.highCount = 1
    else:    out.loRun = 1; out.lowCount  = 1

    for i = lo+1; i < hi; i++:
        bit = (data[i] & mask) ? 1 : 0
        if bit == prev:
            if bit: out.hiRun++ else: out.loRun++
        else:
            if bit == 1:                          // 上升沿
                out.risings++
                out.loMin = min(out.loMin, out.loRun)
                out.loMax = max(out.loMax, out.loRun)
                out.loSum += out.loRun
                out.hiRun = 1
            else:                                 // 下降沿
                out.fallings++
                out.hiMin = min(out.hiMin, out.hiRun)
                out.hiMax = max(out.hiMax, out.hiRun)
                out.hiSum += out.hiRun
                out.cycles++                      // 一个完整高脉冲 = 一个周期
                out.loRun = 1
            prev = bit
        if bit: out.highCount++ else: out.lowCount++

    out.edges = out.risings + out.fallings
    out.duty  = out.highCount / len
    // 脉宽（样本数）：只统计已闭合段（被边沿终止的游程），末尾未闭合段不计
    allPulses = []  // 概念性：由 hiMin/hiMax/loMin/loMax 与总和归纳，无需真建数组
    out.minPulse = min(out.hiMin==Infinity?Infinity:out.hiMin,
                       out.loMin==Infinity?Infinity:out.loMin)
    out.maxPulse = max(out.hiMax, out.loMax)
    totalClosed = out.risings + out.fallings       // 闭合段数
    totalSum    = out.hiSum + out.loSum
    out.avgPulse = totalClosed ? totalSum/totalClosed : 0
    out.freq = out.cycles / (len / rate)           // 完整周期 / 区间时长
    if out.minPulse==Infinity: out.minPulse = 0
    return out
```

**性能要点**：
- 用 `& mask` 判位，不调用 `getter`、不建子数组。
- 8 通道各扫一次 = 8×48e6 ≈ 3.8 亿次循环（约 0.6~1.2s），因此**只对可见通道统计**，并用 `requestIdleCallback` 或分通道 rAF 分片，避免长任务卡 UI。
- 更优做法：一次扫描同时维护 8 组计数器（`for ch` 内联展开为 8 份标量），把 8 次扫描降到 1 次；理由是循环体里 8 路位运算仍是 O(n)，但省去 7 次数组遍历的 cache 冷启动。实现者可按需采用。

**边界处理**：
- `len <= 0`（A=B 或空）→ 全 0 对象，`freq=0`，UI 显示 `—`。
- `len == 1` → `highCount/lowCount` 其一为 1，`duty` 为 0 或 1，无边沿，脉宽全 0，`freq=0`。
- 恒定电平（全高/全低）→ 另一类计数为 0，`duty=1/0`，`cycles=0`，`freq=0`，min/max 脉宽取唯一闭合段或 0。

### 3.3 "脉冲数"的精确定义

**推荐定义：脉冲数 = 区间内的上升沿数（每个 0→1 计一个脉冲），且第一个不完整脉冲计入。**

规则细化：
1. 只数**上升沿**。理由：数字电路中"一个脉冲"通常由其起始（上升沿）界定；下降沿成对出现，数下降沿在相位相反时意义相同但会造成口径混乱。选上升沿与示波器"Pulse"测量惯例一致。
2. 区间从高电平中间开始（前一上升沿在区间外）→ **不计**为脉冲，因为没有上升沿落在区间内。理由：无法确认它是否是完整脉冲，计入会高估。
3. 区间以高电平结束（末尾脉冲未闭合）→ **计入**（上升沿在区间内），但其高脉宽不纳入 min/max/avg 的完整段统计（见 3.2），`freq` 用闭合周期数。理由：计数要覆盖用户看到的每个"跳变起点"，而脉宽/频率统计要避免不完整段污染。
4. `cycles`（频率用）= 下降沿数（完整高-低周期数）；当区间首尾都是低电平时 `cycles = risings`，否则 `cycles = fallings`。实现取 `min(risings, fallings)` 更稳健。

**UI 措辞**：表格列头写"脉冲数(↑)"而非"脉冲数"，消除歧义。理由：显式标注计数口径，用户不会误以为是周期数。

### 3.4 显示设计

- 位置：侧栏 `#measure-list`（全量测量）**下方**新增 `#range-stats` 区块。
- 结构：两个带标题的分区，标题分别为"全量测量（现有）"与"AB 区间统计（新增）"，各自一张表。理由：用户明确要"同时看到全量和区间"，并列分区最直观，不改动现有全量区的 DOM 结构。
- 表格列：`通道 | 脉冲数(↑) | 占空比 | 频率 | 边沿 | 最小脉宽 | 最大脉宽 | 平均脉宽`。
- 通道行按 `visible` 过滤，隐藏通道不显示（与波形一致）。
- 无区间时：区间表显示占位行 `<tr><td colspan=8>设置 A/B 后显示</td></tr>`。
- 脉宽列以**时间单位**显示（`样本数/rate` 经 `fmtTime`），因为用户关心的是时间而非样本数；样本数仅在 AB 读数里给。

### 3.5 前端算还是后端算

**建议：前端本地算，后端 API 保留不改。**

理由：
1. `data` 已在前端内存，`statRange` 是纯 CPU 单次扫描，无网络往返，交互（拖动 A/B）时可即时刷新；调后端每次拖动都要 HTTP + JSON，延迟与抖动不可接受。
2. 后端 `/api/measure?window=[start,end]` 已存在，适合作"导出/深分析"兜底，前端算的结果可与它交叉校验（同一 window 应得到一致 duty/freq——注意后端 `min_pulse/max_pulse` 是样本数，前端展示时需 ×(1/rate) 才能对齐口径）。
3. 不新增依赖，纯 JS 循环，符合项目单体架构。

---

## 4. 集成方案

### 4.1 `draw()` 修改点

**现有顺序**：①清屏填背景 → ②8 横线+10 竖线 → ③扫描 flags[plotW*8] → ④画 8 通道波形 → ⑤画事件三角 → ⑥画光标+样本值。

**改后顺序**（新增 ⑦~⑩，并调整 ②的竖线终点）：

1. 清屏 + 填 panel 背景（不变）。
2. 画 8 条横线（终点 `axisY0`）+ 10 条竖网格线（终点 `axisY0`，不进轴区）——**修改**。
3. 扫描 `flags[plotW*8]`（不变）。
4. 画 8 通道波形（bandH 已用新值）—— **隐含修改**。
5. 画事件三角（不变）。
6. **【新增】区间背景染色 + 顶部区间条**：在光标之前画，避免盖住标记线？建议放在 ⑤之后、⑥之前，让光标始终在最上。
7. **【新增】A/B 标记线 + A/B 标签 + ΔT 浮动读数**。
8. 画光标竖线 + 样本值（原 ⑥，移到标记之后，保证光标最顶）。
9. **【新增】drawTimeline(...)**：最后画，独占轴区 [axisY0,H)，不与波形交叠。

> 顺序原则：轴区最后画（覆盖底部），标记在波形之上、光标之下（光标是高频参照，优先级最高）。

### 4.2 新增 DOM

| id | 位置 | 作用 |
|---|---|---|
| `#btn-mark-ab` | 工具栏（与现有按钮同排） | 切换 AB 放置模式，按下态高亮 |
| `#stat-range` | `index.html` 第 136-143 行 `<footer class="statusbar">` 内，`#stat-cursor` 之后 | 常驻显示 `ΔT/频率/样本数` |
| `#range-stats` | 侧栏 `#measure-list` 之后 | 区间统计区块（标题+表格容器） |

- `#btn-mark-ab` 用 `<button title="AB 区间标记 (M)">AB标记</button>`。
- `#stat-range` 初值 `区间: —`。
- `#range-stats` 初始内含占位表（见 3.4）。
- 不改动现有 5 个 `span` 的 id 与顺序。

### 4.3 新增 CSS

| 类名 | 关键属性 | 用途 |
|---|---|---|
| `.btn-mark-active` | `background: var(--accent); color: #fff` | 放置模式按钮高亮 |
| `.ab-line-a` / `.ab-line-b` | 由 ctx 绘制，无需 CSS（仅按钮图例可用） | 线色规范 |
| `.range-stats` | `margin-top:12px; border-top:1px solid var(--grid); padding-top:8px` | 区块分隔 |
| `.range-stats h3` | `font-size:12px; color:var(--text-dim)` | 小标题 |
| `.range-table` | `width:100%; font:11px var(--mono); border-collapse:collapse` | 表格 |
| `.range-table th,.range-table td` | `padding:2px 4px; text-align:right; border-bottom:1px solid var(--grid)` | 单元格 |

> 画布内元素全部用 `ctx` 绘制，走 CSS 变量读色（`getComputedStyle` 取一次缓存），与现有主题一致。

### 4.4 新增状态

**Waveform 新增**：
- `markers = {a:null, b:null, active:false}`（见 2.1）。
- `axisH = 28`（轴高常量，可放模块顶部 `var AXIS_H = 28`）。
- `bandH` 由 `H/8` 改为 `(H-axisH)/8`（每次 resize 重算）。

**App 新增**（依附现有 App 对象，若不存在则挂在 IIFE 顶层变量）：
- `markMode = 'CURSOR'`（交互状态机当前态，见 2.2）。
- `rangeStats = null`（最近一次 `statRange` 结果数组，按通道）。
- `abDirty = false`（脏标记：A/B 或视图变化后置 true，rAF 中统一重算，避免拖动时每像素算 4800 万样本）。

### 4.5 冲突清单（≥5 条）

1. **左键放光标 vs 放标记**：以 `markers.active` 分流——active 时左键只放 A/B 不设 cursor；非 active 时保留原行为。拖动命中测试优先级高于放置。
2. **缩放/平移时标记位置**：标记存样本索引，缩放只改 `start/span`，`sampleToX` 自动把标记映射到新 x，位置随波形一起缩放（正确行为）；但放置时吸附的整数样本在极端放大后可能落在亚像素，命中容差固定 ±4px，需保证拖动仍可抓住。
3. **视图滚出区间外**：A/B 的 x 超出 `[LABEL_W, W]` 时标记线不画（裁掉），但顶部区间条两端改画方向箭头（◀/▶）指示区间在视图外哪侧；状态栏读数仍保留。
4. **事件三角与标记线视觉冲突**：标记线宽 1.5px 且画在事件之后、光标之前；三角宽约 6px，被线穿过仍可辨识。若实测重叠严重，将标记线改为虚线（`setLineDash([4,3])`）降低遮挡。
5. **通道隐藏时标记线**：仍画跨全高（与 `visible` 无关）。理由：标记是时间轴概念，不是通道概念；隐藏通道不应让时间参照消失。
6. **时间轴挤压波形**：`bandH` 减小 28/8=3.5px/通道；对最小画布高度（如 240px）波形带从 30px 降到 26.5px，仍高于最小可辨高度。若画布高 <120px，建议自动隐藏轴区（`axisH=0`）降级。
7. **区间统计与全量测量口径差异**：同一通道全量用后端 `duty`（0~1）与 `min_pulse`（样本数），区间用前端 `duty`（0~1）与脉宽转秒。UI 必须标注单位，避免用户把"样本数"误读为时间——这是既有 API 的历史口径，不能改后端，只能在前端转换。
8. **拖动 A/B 与拖动手势冲突**：若现有已实现"拖动空白处平移视图"，需在 mousedown 时先判 `hitMarker`，命中则进入 DRAG 并 `stopPropagation`，防止同时触发平移。

---

## 5. 分阶段实施顺序

每阶段可独立验收，前一阶段未通过不进入下一阶段。

**阶段 1 — 时间线（独立可验收）**
- 改 `bandH`、加 `AXIS_H`、实现 `buildTicks` 与 `drawTimeline`、加 `fmtTimeWithUnit`。
- 验收：缩放/平移后刻度位置随时间原点稳定；主标签数在 6~12；相邻标签不重叠。
- 不动 A/B 与统计。

**阶段 2 — AB 区间标记**
- 加 `markers`、`#btn-mark-ab`、`#stat-range`，实现状态机与标记绘制、ΔT 读数。
- 验收：点击两次得到正确 ΔT（与手工 `(b-a)/rate` 一致）；拖动端点 ΔT 实时更新；双击清空；放置模式下不误设 cursor。

**阶段 3 — 区间统计**
- 实现 `statRange`、加 `#range-stats`、分通道 rAF 刷新。
- 验收：构造已知序列得出正确脉冲数/占空比；48e6 样本单通道 <200ms；隐藏通道不出现在表中。

**阶段 4 — 集成打磨**
- 处理 4.5 全部冲突、加快捷键 M、边界降级、与全量测量并列展示。
- 验收：全量+区间同屏；所有冲突场景手工过一遍；无控制台报错。

---

## 6. 验收标准（可测试）

> 均为可执行判定，非"显示正常"式主观描述。

**时间线**
- T1：给定 `span=10e6, rate=100e6`（10ms 跨度）、`plotW=1000px`，`buildTicks` 返回的 `stepSec ∈ {1e-4, 2e-4, 5e-4}`（即 100/200/500µs），主刻度数在 5~11。
- T2：任意缩放下，相邻两个**可见标签**的像素距离 `≥ (w_i+w_j)/2 + 8`（用 1.3 的公式验证，抽查 3 个缩放级别）。
- T3：同一绝对时间在 3 次不同 `start` 下的标签文本完全相同（证明原点固定在采集起点）。
- T4：`stepSec` 钳位：构造 `spanSec=1e-12` 时返回 `1e-9`；`spanSec=1e6` 时返回 `1000`。

**AB 区间**
- A1：`a=1000, b=1500, rate=1e6` → ΔT 显示 `500.0 µs`，样本数 `500`，频率 `2.0 kHz`。
- A2：mousedown 落在标记线 x±3px 内 → `mode` 进入 DRAG；±6px 外 → 不进入（证明命中容差=4px）。
- A3：`markers.active=true` 时单击 → `cursor` 值不变（证明不误设光标）。
- A4：反向放置（先点右侧再点左侧）→ 自动交换后 `a<b`，ΔT 为正。
- A5：双击或右键标记 → `a=b=null`，`stat-range` 回到 `区间: —`。

**区间统计**
- S1：序列 `[0,0,1,1,1,0,0]`（lo=0,hi=7）→ `risings=1, fallings=1, highCount=3, lowCount=4, duty=3/7≈0.4286, cycles=1`。
- S2：恒定高电平 100 样本 → `risings=0, fallings=0, duty=1, freq=0, minPulse=0`（不崩、不除零）。
- S3：`len=1` → 不抛异常，返回对象字段齐全。
- S4：48,000,000 样本单通道 `statRange` 用 `performance.now()` 测 <200ms（在目标机 Chrome 上）。
- S5：前端算出的 `duty` 与后端 `/api/measure?window=[lo,hi]` 返回值在 ±1e-6 内一致。

**集成**
- I1：`draw()` 改后绘制顺序与 4.1 列表完全一致（代码审阅）。
- I2：6 个场景下无控制台错误：隐藏通道、区间滚出视图、极端缩小(<1ns/格)、极端放大、空区间、拖动中切换缩放。
- I3：三个新增 DOM id 存在且初值正确（`#btn-mark-ab` 未按下、`#stat-range` 为 `区间: —`、`#range-stats` 有占位行）。

---

## 附：关键决策速查（含理由摘要）

| 决策 | 选择 | 一句话理由 |
|---|---|---|
| 轴高 | 28px | 容纳 11px 标签+padding，仅压缩波形 7% |
| 时间原点 | 采集起点 | 跨视图稳定，符合"时间概念"直觉 |
| A/B 精度 | 整数样本 | 与现有全部读数口径统一，ΔT 可复现 |
| 脉冲定义 | 数上升沿，首脉冲计入 | 与示波器惯例一致，语义单一 |
| 计算位置 | 前端本地 | 无网络延迟，拖动可即时刷新 |
| 读数位置 | 画布浮动+状态栏 | 就近可读 + 固定位置可截图 |
| 清除方式 | 双击/右键标记 | 不占用左键（留给放置/拖动） |
| 轴区标签列 | 留空 | 语义分离，避免误读 |
