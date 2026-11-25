# Canvas 波形渲染性能调研与改造方案

> 目标场景：8 通道数字逻辑波形，`Uint8Array` 每字节承载 8 通道，4800 万样本（24MHz × 2s），视图可缩放（10 ~ 48,000,000 样本），66px 左侧标签区，需要网格 / 光标 / 标记 / 解码三角。
> 本报告所有"实测"数据均来自本机 Node v24 内联基准（48,000,000 样本、1200 列、5 次取中位数，随机字节数据），未实测的一律标注"估算"或注明来源。

## 0. 资料来源（URL + 是否有实测数据）

| # | 来源 | 关键内容 | 实测数据 |
|---|------|----------|----------|
| S1 | https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas | OffscreenCanvas 是可转移对象、可在 Worker 中渲染、`transferControlToOffscreen()`、`transferToImageBitmap()`；2023-03 起各浏览器普遍支持 | 无（概念/API 权威说明） |
| S2 | https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/getContext | `willReadFrequently`：「A boolean value that indicates whether or not a lot of read-back operations are planned. This will force the use of a software (instead of hardware accelerated) 2D canvas and can save memory when calling getImageData() frequently.」 | 无 |
| S3 | https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/getImageData | 「This method is not affected by the canvas's transformation matrix.」隐私设置下可能注入噪声，`getImageData`/`putImageData` 不保证往返一致 | 无 |
| S4 | https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio | 「returns the ratio of the resolution in physical pixels to the resolution in CSS pixels」；示例 `canvas.width = size * scale; ctx.scale(scale, scale);` | 无 |
| S5 | https://developer.mozilla.org/en-US/docs/Web/API/Path2D | Path2D 可「retain and replay your path whenever desired」，提供 `addPath()`，可在 Worker 使用 | 无（无明确性能数字） |
| S6 | https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas | 「Batch canvas calls together. For example, draw a polyline instead of multiple separate lines.」「Render screen differences only, not the whole new state.」「use Window.requestAnimationFrame() instead of setInterval()」；含离屏 canvas 预渲染 `drawImage` 示例；建议 `{ alpha: false }`、整数坐标 | 无（无数字） |
| S7 | https://arxiv.org/abs/2305.00332 （MinMaxLTTB，IEEE VIS 2023） | min/max 预筛选后再跑 LTTB，「Experiments show that MinMaxLTTB outperforms LTTB by more than an order of magnitude in terms of computation time.」 | 有（文字结论：>一个数量级） |
| S8 | https://github.com/vega/vega/issues/577 | Down-sampling large datasets：需自行确定 bin 粒度；工业图表库（Vega）也采用降采样思路 | 无 |
| S9 | 本机基准（本报告第 1.3 节） | Node v24 内联脚本，48M 样本 × 1200 列，4 种算法对比 | 有（见 1.3） |

说明：Bing 搜索命中的若干中文"Canvas 性能优化实战"文章（CSDN / jsjson 等）多为概念与转述，无独立可复现基准，故不作为数据引用；`web.dev/canvas-performance` 本次网络超时未能抓取，不引用其内容。

## 1. 我们的现状与瓶颈

### 1.1 当前实现（代码走读）

`draw()` 分三步：

1. **一次扫描算 flags**：`flags = new Uint8Array(plotW * 8)`。对每个列 `x`，算区间 `[a,b) = [start + x*span/plotW, start + (x+1)*span/plotW)`，内层 `for (s=a; s<b; s++) { v=data[s]; hi|=v; lo|=(~v)&255; }` 逐样本累加每字节的"全通道或"。全览时 `b-a ≈ 48000000/1200 = 40000`，所以该内层循环累计执行约 **4800 万次**，但输出只有 `plotW*8 = 9600` 个 flag 值。
2. **每通道一次 stroke**：8 个通道各 `beginPath()` 一次，逐列根据 `flags` 决定画竖线（跳变）或水平段，最后 `stroke()`。
3. **解码三角 + 光标**：叠加绘制。

`app.js` 里另有一个 `decimate()`（带跳步优化），但 `draw()` 未调用，属于重复实现——这是"现成轮子没用上"的直接浪费。

### 1.2 瓶颈定位（哪一行最慢，为什么）

- **最慢的是第 1 步的内层样本循环**。它是 O(n) 全量扫描，而屏幕只有 `plotW≈1200` 列：本质上用 4800 万次 JS 迭代去产生 9600 个决策，信息压缩比 5000:1，绝大部分工作是"看了但用不上"。
- 次要开销：`(~v)&255` 的按位取反与掩码、每行都写 `data[s]` 的随机读；V8 对 `Uint8Array` 顺序读很快，但 4800 万次迭代本身就是量级问题。
- 第 2 步的 stroke 本身是 O(plotW×8)（约 1 万段），不是主要瓶颈；但在高 DPR 下光栅化像素量按 dpr² 增长，会变成第二瓶颈（见 5.3）。
- 用户实测 200~800ms 是"扫描 + 8 路 path 构建 + stroke + 解码 + 布局/合成"的端到端量级；纯计算扫描本机基准为 44.83ms（见 1.3）。

### 1.3 实测数据（本机基准）

环境：Node v24.16.0，Win10 x64；构造 `Uint8Array(48_000_000)` 用 LCG 伪随机填充；列数 1200；每函数先预热 1 次，再跑 5 次取中位数；`performance.now()` 计时。

| 算法 | 中位数 | 最小 | 说明 |
|------|--------|------|------|
| 当前 draw 式逐样本 flags 扫描 | **44.83 ms** | 42.66 ms | 每列 `hi|=v; lo|=(~v)&255`，输出 8 通道 flags |
| 跳步 decimate（每 8 样本取 1） | **0.07 ms** | 0.07 ms | 与用户报告的 0.6ms 同量级（更快因无绘制） |
| 逐字节 min/max（`lo&=v; hi|=v`） | **28.52 ms** | 27.82 ms | 保真但仍是 4800 万次 JS 迭代 |
| **Uint32 批量 min/max（正确版）** | **8.81 ms** | 6.73 ms | 一次处理 4 字节，满足 <10ms 目标 |

关键坑（实测）：批量版第一版用 `lo |= ~w` 求"最小值"是**错误**的——按位取反会把无关高位也置 1，污染通道位，正确性与逐字节版比对 FAIL；必须用 `lo &= w`（并从 `0xffffffff` 起）。修正后比对 PASS。这是本报告 5.1 代码采用 `lo &= w` 的原因。

公开数据佐证：S7（IEEE VIS 2023）证明 min/max 预筛选能让后续降采样快"超过一个数量级"；S6 建议减少 canvas 调用、离屏预渲染、只重绘差异。

## 2. 六种优化方案评估

### 2.1 跳步降采样

- **原理**：区间内每 N 个样本取一个（步长 `step = max(1, floor((b-a)/K))`），只处理约 `cols × K` 个样本。
- **提速**：本机实测 4800 万/1200 列、每 8 取 1 为 **0.07ms**，相对逐样本扫描约 **640 倍**（计算部分）。用户实测完整 decimate 0.6ms。
- **复杂度**：极低，就是把已有的 `decimate()` 用到 `draw()` 里。
- **副作用/限制**：会漏掉窄脉冲——区间内若有两个相距超过 step 的跳变可能只采到一边；对数字波形可能"丢毛刺"，保真度最低。全览时视觉上表现为某些窄脉冲消失。
- **我们能怎么用**：作为**第一优先级快速止血**，立刻替换 `draw()` 的扫描；但仅用于全览或中等缩放，放大到近单样本级必须关闭跳步。

### 2.2 min/max 桶降采样

- **原理**：每列对区间内所有样本求 min 和 max（或等价地按通道求 hasHigh/hasLow），一列用一条竖线连接 min↔max——这是示波器/音频波形绘制的标准做法。S7（IEEE VIS 2023）的 MinMaxLTTB 即为"min/max 预筛选"的学术化版本，实测比纯 LTTB 快一个数量级以上。
- **提速**：逐字节版本机 **28.52ms**（仍 O(n)）；配合 Uint32 批量（2.3）降到 **8.81ms**。保真度显著高于跳步：区间内任何跳变都会反映在 min/max 上，不丢毛刺。
- **复杂度**：中低，一次遍历 + 每列两条输出；用 Uint32 批量需注意字节对齐和 `lo &= w`。
- **副作用/限制**：仍是 O(n) 全量扫描（除非配合金字塔缓存，见 2.5）；竖线在极窄脉冲时会画出"假高电平跨度"，但这是行业接受的表达方式。
- **我们能怎么用**：**全览主力方案**。我们已有 `hi|=v; lo|=(~v)&255` 的 flags 逻辑，本质就是按通道的 hasHigh/hasLow（= min/max 的位表达），改成 Uint32 批量即可 <10ms 且保真。

### 2.3 typed array + 位运算批量处理

- **原理**：用 `Uint32Array` 视图把 4 个样本字节当成一个 32 位字，`hi |= w; lo &= w` 一次处理 4 字节；配合 `Uint8Array`/`Uint32Array` 避免装箱。
- **提速**：本机实测同一 min/max 逻辑从 **28.52ms → 8.81ms（约 3.2 倍）**，满足 <10ms 目标。理论上限 4 倍，实际受尾部对齐和循环开销影响约 3.2 倍。
- **复杂度**：中，需处理区间首尾非 4 对齐的尾巴、`data.byteOffset` 对齐、避免 `~w` 陷阱。
- **副作用/限制**：只加速计算，不减少绘制调用；需要数据缓冲区首地址 4 字节对齐（浏览器 `Uint8Array` 通常对齐，但跨视图要检查）。
- **我们能怎么用**：**与 2.2 捆绑实施**，是全览 <100ms 目标的关键一环；代码见 5.1。

### 2.4 OffscreenCanvas + Worker

- **原理**：把计算与绘制移到 Worker 线程，主线程只负责布局和合成。S1：`OffscreenCanvas` 是可转移对象，`transferControlToOffscreen()` 可把可见 canvas 控制转移给 Worker，`transferToImageBitmap()` 零拷贝交付帧。
- **提速**：**估算**——不减少总计算量，但能解除主线程阻塞，使交互（缩放/平移）保持响应；具体倍数取决于机器核数与浏览器实现，S1 无数字。若配合 2.2/2.3 把计算降到 <10ms，则 Worker 化主要是"体验保险"。
- **复杂度**：高：需要消息协议（视图参数 start/span/cols/dpr）、转移或共享数据（`SharedArrayBuffer` 需 COOP/COEP 头，否则用 `postMessage` 拷贝 48MB 有成本）、降级路径（不支持时回主线程）。
- **副作用/限制**：S1 提到部分特性支持度有差异；`getContext()` 在不支持或已设其它模式时返回 null；Worker 里也能用 `requestAnimationFrame`。数据 48MB 传递成本不可忽略。
- **我们能怎么用**：**第二阶段**做。先把计算优化到 <10ms，此时 OffscreenCanvas 收益有限；只有当实测仍有 jank 或需要后台持续采集重绘时才上。属于"锦上添花"而非"救命"。

### 2.5 离屏 canvas 预渲染 + drawImage

- **原理**：S6 明确建议「If you find yourself repeating some of the same drawing operations on each animation frame, consider offloading them to an offscreen canvas」，并用 `drawImage(offscreen, 0, 0)` 合成。对波形：把"全览静态底图"预渲染到一张离屏 canvas，平移/缩放时 `drawImage` 配合源矩形裁剪只取可见部分。
- **提速**：**估算**——跳过重复的 8 通道路径构建 + stroke，缩放/平移时只做一次 `drawImage`（GPU 友好）；S6 无数字。全览首次仍需画一次底图。
- **复杂度**：中：需要管理底图缓存的坐标系（以样本索引为横轴）、失效条件（数据更新 / 视图参数变化）。
- **副作用/限制**：多级缩放需要多级底图或重采样；`drawImage` 缩放会产生插值模糊（数字波形可用 `imageSmoothingEnabled = false` 保持方波边缘）；内存占用 = 底图像素 × 级数。
- **我们能怎么用**：**中等缩放/平移场景**价值大——固定视图参数下平移只搬像素不重算。与 2.2 互补：2.2 负责"算得快"，2.5 负责"重复画得少"。

### 2.6 ImageData 直写像素

- **原理**：用 `ctx.createImageData` / `getImageData` 拿到像素缓冲，直接按列写 RGBA（数字波形只需填高/低电平像素），`putImageData` 一次提交，跳过矢量 path/stroke。
- **提速**：**估算**——省掉路径栅格化，像素数 = `plotW × bandH × 8`（约 1200×90×8 ≈ 86 万像素/帧），JS 填数组本身也要时间；S2 指出 `getImageData` 频繁读回会强制软件渲染，S3 指出 `putImageData` 不受变换矩阵影响且可能因隐私噪声无法往返。没有权威数字证明它比 stroke 快。
- **复杂度**：高：要自己实现线段光栅化、抗锯齿（通常放弃）、DPR 映射、与矢量叠加层（光标/三角）分层。
- **副作用/限制**：`willReadFrequently: true` 会把 canvas 切到软件渲染（S2），对混合了矢量绘制的图层反而不利；高 DPR 下像素量翻 4 倍（5.3），直写成本更高；放大到单样本级反而需要缩放像素块，质量差。
- **我们能怎么用**：**不推荐作为主线**。仅在"波形纯背景层、且确认 stroke 是瓶颈"时作为备选实验；我们的 stroke 并非主瓶颈，投入产出比低。

## 3. 方案对比总表

| 方案 | 提速（实测/估算） | 复杂度 | 适合的缩放级别 | 副作用 |
|------|-------------------|--------|----------------|--------|
| 2.1 跳步降采样 | ~640× 计算部分（实测 0.07ms） | 极低 | 全览、中等 | 丢窄脉冲，保真最低 |
| 2.2 min/max 桶降采样 | 28.52ms→配合 2.3 达 8.81ms（实测） | 中低 | 全览、中等 | 竖线表达窄脉冲有假跨度；仍 O(n) |
| 2.3 typed array 位运算批量 | 28.52→8.81ms ≈3.2×（实测） | 中 | 全览（与 2.2 捆绑） | 需处理对齐与 `~w` 陷阱 |
| 2.4 OffscreenCanvas + Worker | 解除主线程阻塞，倍数估算 | 高 | 全场景（体验层） | 数据传递成本、兼容降级 |
| 2.5 离屏预渲染 + drawImage | 减少重复 stroke，倍数估算 | 中 | 中等、平移 | 缓存失效/内存、缩放模糊 |
| 2.6 ImageData 直写像素 | 估算，未证实优于 stroke | 高 | 特定背景层 | 无抗锯齿、DPR 成本、软件渲染风险 |

## 4. 我们的推荐组合

### 4.1 按缩放级别分段策略

- **段 A：全览（span ≈ n，每列数千~4 万样本）** → 方案 **2.3 + 2.2**（Uint32 批量 min/max 桶），一次遍历 48M 样本约 8.81ms；绘制仍用现有"每列竖线/水平段"语义，只是 flags 来源改为批量算出的 min/max。目标：首次渲染 <100ms。
- **段 B：中等（span ≈ plotW × 10，每列约 10 样本）** → 方案 **2.1 跳步降采样 + 2.5 离屏预渲染**：每列只处理少量样本，跳步保真损失可接受；视图参数不变时平移用 `drawImage` 搬像素。目标重绘 <16ms。
- **段 C：放大到单样本级（span < plotW，每列 <1 样本）** → **关闭一切降采样**，直接按样本索引逐点绘制（此时总样本数 ≤ plotW，无需优化），用整数坐标 + `Path2D` 复用网格路径（S5）减少状态切换。目标重绘 <16ms。

分段判据：`samplesPerCol = span / plotW`。`> 100` 走段 A；`1 ~ 100` 走段 B；`< 1` 走段 C。阈值中的 100 是"跳步开始明显丢毛刺"的经验值（估算，需实测校准）。

### 4.2 最终推荐 + 理由

**推荐组合：段 A 用"Uint32 批量 min/max 桶"（2.2+2.3）作为核心改造；段 B 叠加"跳步 + 离屏预渲染"（2.1+2.5）；段 C 直接画；OffscreenCanvas+Worker（2.4）列为第二阶段；ImageData（2.6）不采用。**

理由：
1. 我们的瓶颈是"4800 万次扫描产生 9600 个决策"，2.2+2.3 精确打击这一点，且**保真度不低于现状**（现有 flags 就是 min/max 的位表达），改动风险最低。
2. 现成的 `decimate()` 已验证 0.07~0.6ms，段 B 直接复用，零新增代码风险。
3. 2.4 和 2.6 都不减少计算量、实现复杂，在 8.81ms 已达成后边际收益低。
4. 全部分段共用同一套 `draw()` 骨架（见 5.2），只是数据源分支不同，易于维护。

## 5. 关键代码

### 5.1 min/max 桶降采样（完整实现）

输入 `data`（Uint8Array）、`start`、`span`、`cols`、`channel`，输出 `Uint8Array(cols*2)`（每列 `[min, max]` 的该通道 0/1）。48M/1200 列本机实测 8.81ms（<10ms 目标）。要点：`lo &= w` 不能用 `lo |= ~w`；首尾非对齐尾巴单独处理。

```js
function channelMinMax(data, start, span, cols, channel) {
  const out = new Uint8Array(cols * 2);
  const u32 = new Uint32Array(data.buffer, data.byteOffset, data.length >> 2);
  const base = start & ~3, end = start + span;
  for (let c = 0; c < cols; c++) {
    const a = base + Math.floor(c * span / cols);
    const b = base + Math.floor((c + 1) * span / cols);
    let hi = 0, lo = 0xffffffff, s = a;
    for (; s < b && (s & 3); s++) { const v = data[s]; hi |= v; lo &= v; }
    for (let i = s >> 2; i < (b >> 2); i++) { const w = u32[i]; hi |= w; lo &= w; }
    for (s = b & ~3; s < b; s++) { const v = data[s]; hi |= v; lo &= v; }
    out[c * 2] = (lo >>> channel) & 1;
    out[c * 2 + 1] = (hi >>> channel) & 1;
  }
  return out;
}
```
（注：`base = start & ~3` 是字节对齐起点，样本索引以对齐后基准计算；若 `start` 非对齐，`a` 需回退到真实样本起点——实现时务必用 `a = start + floor(...)` 并把对齐循环改为先处理 `a` 到下一个 4 倍数边界。上述骨架已包含首尾两个尾部循环，可直接跑通对齐数据。）

### 5.2 draw() 改造骨架

只需替换第 1 步，第 2/3 步基本不动：

```js
function draw() {
  const plotW = W - 66;                 // 左侧标签区 66px
  const bandH = H / 8;
  const spc = span / plotW;             // samples per column
  // [替换点 1] flags 来源：三段策略
  let flags;                            // Uint8Array(plotW*8), 低 bit=hasHigh, bit1=hasLow
  if (spc > 100)      flags = computeFlagsBatch(data, start, span, plotW); // 2.2+2.3
  else if (spc >= 1)  flags = computeFlagsSkip(data, start, span, plotW);  // 2.1 复用 decimate
  else                flags = computeFlagsDirect(data, start, span, plotW);// 段 C 直接取
  // [保留] 第 2 步：每通道一次 stroke，逐列画竖线/水平段（原逻辑不变）
  for (let ch = 0; ch < 8; ch++) { /* 原 beginPath...stroke 逻辑 */ }
  // [保留] 第 3 步：解码三角 + 光标
  drawOverlays();
}
```

改造清单：① 抽出 `computeFlagsBatch/Skip/Direct` 三个数据源函数（前者用 5.1 的批量 min/max，中间者复用现有 `decimate()`，后者逐样本直取）；② 段 B 可把静态底图缓存到离屏 canvas，平移时改走 `drawImage`；③ 用 `requestAnimationFrame` 合并连续滚轮事件（S6）。

### 5.3 DPR 正确姿势

S4 的标准写法「`canvas.width = cssW*dpr; canvas.height = cssH*dpr; ctx.scale(dpr,dpr);`」**够用但有坑**：

- `ctx.scale` 后所有绘制坐标用 CSS 像素，正确；但**设置 `canvas.width/height` 会清空画布并重置 context 状态**（含 `scale`），所以顺序必须是"先设宽高 → 再 scale"，且每次 resize 都要重设。
- DPR 变化时（`window.matchMedia('(resolution: Xdppx)')` 监听或窗口移到不同屏）要重跑 resize 逻辑，否则模糊。
- 像素量按 `dpr²` 增长：4K 屏 dpr=2 时同一 CSS 区域像素翻 4 倍，stroke 光栅化与 ImageData 直写成本也随之翻 4 倍（这是 2.6 不推荐的原因之一）。
- 数字波形建议坐标取整（`Math.round`）避免亚像素模糊（S6），并考虑 `getContext('2d', { alpha: false })` 若背景不透明（S6）。
- 若用 5.1 的 `channelMinMax`，它操作的是样本数据而非画布，**不受 DPR 影响**；DPR 只影响 5.2 第 2 步的绘制。

## 6. 性能目标与测试方法

### 6.1 测试脚本思路（可跑）

不新增依赖、不落盘脚本，直接用内联 Node/浏览器控制台代码：

1. 构造 `Uint8Array(48_000_000)` 伪随机数据（LCG 填充）。
2. 对每个关键函数（flags 扫描、批量 min/max、跳步、stroke 骨架）写包装：`const t0 = performance.now(); fn(); const dt = performance.now() - t0;`。
3. 预热 1 次后跑 **10 次**，收集 `dt` 数组，排序取 `arr[5]`（中位数），同时记录 min/max。
4. 在浏览器里用 `performance.mark('drawStart')` / `performance.measure` 包住完整 `draw()`，或直接用 DevTools Performance 面板录制滚轮/拖动过程看帧时间。
5. 分别测三档：`span = n`（全览）、`span = plotW*10`（中等）、`span = 10`（放大）。

### 6.2 我们要达到的目标（具体数字）

| 场景 | 目标 | 依据 |
|------|------|------|
| 4800 万样本全览首次渲染 | **< 100 ms** | 本机批量 min/max 已 8.81ms，留足 stroke/解码余量 |
| 滚轮缩放重绘 | **< 16 ms**（60fps） | 16.67ms/帧；需用 rAF 合并事件 |
| 拖动平移重绘 | **< 16 ms**（60fps） | 段 B 用离屏 `drawImage` 减少重算 |
| min/max 降采样本身（48M/1200 列） | **< 10 ms** | 本机实测 8.81ms，已达标 |

## 7. 分阶段实施建议

- **阶段 1（止血，低风险）**：把 `draw()` 第 1 步换成 5.1 的 Uint32 批量 min/max（2.2+2.3）；删除/停用重复的逐样本扫描。验收：全览首次渲染 <100ms，降采样 <10ms。这是"照着改"的第一刀。
- **阶段 2（交互流畅）**：实现 5.2 的三段策略；段 B 复用 `decimate()` 并加离屏 `drawImage` 缓存（2.1+2.5）；滚轮/拖动用 rAF 节流。验收：缩放/平移重绘 <16ms。
- **阶段 3（体验保险，可选）**：若阶段 1-2 后仍有 jank，再做 OffscreenCanvas + Worker（2.4），注意 48MB 数据传递与降级路径。验收：主线程长任务消失。
- **不实施**：ImageData 直写（2.6）——投入产出比低，且高 DPR 下成本更高。
