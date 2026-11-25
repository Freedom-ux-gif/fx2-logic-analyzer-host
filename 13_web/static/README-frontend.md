# 逻辑分析仪前端说明

## 文件说明

| 文件 | 作用 |
|---|---|
| `index.html` | 单页应用骨架：顶栏（设备徽章 / 采样率 / 时长 / 采集 / 主题）、波形区、通道与测量侧栏、状态栏、协议解码抽屉。 |
| `style.css` | 深色科技风样式 + 浅色主题（CSS 变量切换）、按钮三态、状态徽章、进度条、自定义滚动条、<900px 响应式侧栏。 |
| `app.js` | 核心逻辑，IIFE 组织，无 ES module：`Api`（fetch 封装）、`Waveform`（Canvas 降采样渲染）、`Measurer`、`Decoder`、`App`（主控）。 |
| `mock_server.py` | 纯标准库假后端，实现全部 API，返回 50 kHz 方波合成数据，用于独立自测。 |
| `selftest.html` | 不依赖外部库的断言页，可直接 `file://` 打开运行，验证降采样/位提取/时间换算/颜色表/API 错误处理。 |

## 怎么单独验证前端

1. 启动 mock 后端（只监听 127.0.0.1:8421，不碰真实设备）：

   ```bash
   cd 13_web/static
   python -I mock_server.py --port 8421
   ```

2. 浏览器打开 `http://127.0.0.1:8421/`。
3. 操作流程：
   - 顶栏选择采样率（默认 1 MHz）和时长（默认 1 s），点「▶ 开始采集」。
   - 采集期间顶栏显示黄色进度条、设备徽章变黄；完成后波形区显示 8 通道方波。
   - 滚轮缩放波形（以鼠标为锚点），右键拖动或按住空格拖动平移，左键放置光标，双击复位。
   - 侧栏勾选/改色通道；「测量」区显示频率、占空比、脉宽等。
   - 点「⚙ 协议解码」，选 UART/I2C/SPI/CAN，填参数后点「解码」，结果表格与波形上的彩色三角标记联动。
   - 打开「触发采集」开关可配置边沿/电平/脉宽触发与预触发比例，走 `/api/capture/triggered`。
   - 底部状态栏显示样本数、视图范围、光标值、完整 `saved_path`，点「📁 打开文件夹」调用对应 API。
   - 点「◐ 主题」在深色/浅色间切换（保存到 localStorage）。
4. 单独跑断言：浏览器打开 `file:///./selftest.html`（相对本目录），应显示 `ALL TESTS PASSED (n)`。
5. 后端不可用时页面顶部会显示醒目提示并禁用采集按钮；所有 API 错误以 toast 显示（3 秒消失，不使用 `alert()`）。

## 降采样原理

4800 万样本无法逐点绘制（Canvas 宽度只有约 1200 像素，浏览器也扛不住 4800 万条线段）。
做法是把可见样本范围按**像素列**分组：第 `x` 列对应样本区间 `[start + x*span/cols, start + (x+1)*span/cols)`。

对每列的样本做位运算聚合：

```js
hi |= v;          // 该列出现过的所有高电平（按位或）
lo |= (~v) & 255; // 该列出现过的所有低电平
flag = (hi & bit ? 1 : 0) | (lo & bit ? 2 : 0);
```

- `flag === 1`：该列全为高，画顶部水平线。
- `flag === 2`：该列全为低，画底部水平线。
- `flag === 3`：该列既有高也有低，画一条竖直实线（数字示波器标准画法，避免混叠时丢边沿）。

关键约束：
- 数据始终保留为 `Uint8Array`，**不转普通 JS 数组**、不逐样本创建 JS 对象。
- 扫描复杂度 O(可见样本数)，但仅当缩小到全览时可见样本才多；总体内存为每列 1 字节 × 8 通道。
- 用 `requestAnimationFrame` 合并重绘请求；缩放时重新降采样，而不是拉伸位图。
- Canvas 按 `devicePixelRatio` 放大物理像素，高分屏清晰。

## 和后端的对接点

所有 JSON 接口返回 `{ok:bool, ...}`，失败 `{ok:false, error:"中文错误"}`。

| 方法 | 路径 | 请求 | 响应 | 前端状态 |
|---|---|---|---|---|
| GET | `/api/status` | — | `{ok, device:{present,initialized,endpoints}, rates:[{hz,name}], version}` | 已实现：设备徽章/横幅/采样率列表 |
| POST | `/api/capture` | `{rate_hz,seconds}` | `{ok,id,n_samples,rate_hz,elapsed,achievement,saved_path}` | 已实现 |
| GET | `/api/data/<id>` | — | 二进制 `application/octet-stream`（每字节 8 通道） | 已实现：arrayBuffer → Uint8Array；CHn=bitn |
| POST | `/api/capture/triggered` | `{rate_hz,seconds,trigger,pre_ratio}` | 同上 + `{found,trigger_offset}` | 已实现：触发表单 |
| POST | `/api/decode` | `{id,protocol,params}` | `{ok,events:[{kind,start_sample,end_sample,data}],summary}` | 已实现：四种协议表单 + 表格 + 波形标记 |
| GET | `/api/measure/<id>` | `?window=[s,e]` 可选 | `{ok,channels:[{channel,edges,freq,duty,high_ratio,min_pulse,max_pulse}]}` | 已实现：侧栏测量卡片（未传 window，待联调窗口测量） |
| POST | `/api/save` | `{id,format,channels}` | `{ok,path}` | 后端已实现接口，前端暂未加保存按钮（待联调） |
| GET | `/api/open-folder` | — | `{ok,path}` | 已实现：状态栏打开文件夹 |
| GET | `/api/events` | — | SSE `progress` / `done` | 已实现：采集进度条 |

关键数据契约：`/api/data/<id>` 每字节代表 8 通道，CHn 对应 bitn；`events.start_sample/end_sample` 是样本索引，乘以 `1/rate` 得秒。

> 说明：前端按契约编写并用 `mock_server.py` 自测；真实后端由另一执行手开发中，联调时只需保证上述路径与字段一致即可，无需改动前端结构。
