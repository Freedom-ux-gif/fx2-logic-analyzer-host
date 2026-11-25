# 逻辑分析仪网页上位机（本地 HTTP 后端）

一个运行在本机的网页上位机后端。双击 `start.bat` 后浏览器自动打开，无需命令行。

## 怎么启动

- 最简单：双击 `start.bat`（UTF-8 中文窗口，出错时按任意键关闭）。
- 命令行：`python -I launcher.py`
- 不想自动开浏览器：`python -I launcher.py --no-browser`
- 指定端口：`python -I launcher.py --port 8421`
- 只做自检：`python -I launcher.py --check`

如果提示 `python 不是内部或外部命令`，按 `start.bat` 顶部注释把 `python` 换成完整路径。

## 文件存哪

采集数据自动保存到 **`文档\LogicCapture\`**（即 `C:\Users\你的用户名\Documents\LogicCapture`），
文件名形如 `capture_20261125_123456_1MHz.bin`。页面上的「打开文件夹」按钮可直接打开该目录。
`--check` 自检和每次请求都会写日志到 `logs\server_YYYYmmdd.log`。

## API 表

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 `static/index.html`（若不存在返回占位页说明前端未就绪） |
| GET | `/static/*` | 静态文件（.js/.css/.html/.ico），必须防目录穿越 |
| GET | `/api/status` | `{ok, device:{present, initialized, endpoints:[...]}, rates:[{hz,name}], version}` |
| POST | `/api/capture` | body JSON `{rate_hz, seconds}` → 执行采集 → 返回 `{ok, id, n_samples, rate_hz, elapsed, achievement, saved_path}` |
| GET | `/api/data/<id>` | **二进制** `application/octet-stream`，返回该次采集原始字节 |
| POST | `/api/capture/triggered` | body `{rate_hz, seconds, trigger:{type, channel, ...}, pre_ratio}` → 返回同上 + `{found, trigger_offset}` |
| POST | `/api/decode` | body `{id, protocol, params:{...}}` → 返回 `{ok, events:[{kind, start_sample, end_sample, data}], summary}` |
| GET | `/api/measure/<id>?window=[start,end]` | 返回各通道统计 `{channel, edges, freq, duty, high_ratio, min_pulse, max_pulse}` |
| POST | `/api/save` | body `{id, format:'csv'|'vcd'|'bin', channels:[...]}` → 存到文档目录 → 返回 `{ok, path}` |
| GET | `/api/open-folder` | 打开采集文件所在目录（Windows `explorer`），返回 `{ok, path}` |
| GET | `/api/events` | **SSE 流**，推送 `{type:'progress', value:0..1}` 和 `{type:'done', id}` |

`/api/status` 额外返回 `occupied`（布尔）：为真时表示设备被其它程序占用，页面应提示用户关闭其它采集程序。
还返回 `signal_present`（布尔，最近一次采集任意通道有无跳变）：为 false 时页面可提示「未检测到信号，请检查接线」。

## 采集样本数说明

底层 `capture_timed()` 在设备收到启动命令前会先跑 0.2 秒预读线程，连续多次采集时还会带入上次残留字节
（实测同一设备连续三次 0.5 秒采集返回 655360 / 851968 / 851968 字节，而不是 500000）。
因此本后端在保存前按 `采样率 × 请求时长` 裁剪到用户请求的窗口，保证 `n_samples` 与请求一致；
裁剪是修正残留数据，不是掩盖问题。

## 常见问题

- **设备没初始化 / 缺 0x82 端点**：先启动一次 Logic.exe 初始化设备，再刷新页面。
- **设备打开失败：可能被其它程序占用**：关闭正在运行的 `LogicScope.exe` / `Logic.exe` 后重试。
- **端口被占用**：自动从 8421 往后试到 8430，实际端口见控制台输出。
- **浏览器没自动打开**：手动访问控制台打印的地址（如 `http://127.0.0.1:8421`）。

## 已知限制

- 单用户使用，无鉴权机制，仅限本机。
- 只监听 `127.0.0.1`，不暴露到局域网。
- 采集时设备独占：同一时刻只能进行一次采集，冲突时返回 409。
- 内存里只保留最近 20 次采集元数据（不删除已落盘的文件）。
