# 后端 API 审计与扩展设计

## 0. 审计范围与方法

- 审计对象：`13_web/server.py`（实读 **735 行**，以代码为准）、`13_web/launcher.py`（实读 **153 行**）。
- 辅助证据：`09_app/` 下 4 个解码器仅 grep `def decode_` 签名；`09_app/exporter.py` 仅 grep `def` 签名。
- 方法：逐路由把「大脑给的经验清单」与真实处理函数对照，差异以代码为准；再按数据结构（`STATE`、`read_capture`、`save_capture`、`safe_handler`、`ApiError`）推导新增 API，不凭空设计。
- 输入清单行数与实际有出入：契约写 server.py 731 行 / launcher.py 122 行，实读为 735 / 153 行。内容一致，属统计口径差异，记录于此，不影响设计。
- 本任务**只做设计**，未修改任何现有文件，未新增依赖。

## 1. 现有 API 与实际代码的差异

逐条核对（路由分发见 `_route_get` 434-449 行、`_route_post` 451-460 行）：

| # | 路由 | 大脑清单 | 代码实际 | 是否一致 |
|---|------|---------|---------|---------|
| 1 | `GET /` | static/index.html | `handle_root`：有 index.html 则读它，否则返回内置提示 HTML | 一致（多了降级分支） |
| 2 | `GET /static/*` | 静态文件、防穿越 | 白名单后缀 7 种；`..` 段 403；绝对路径校验；缺失 404 | 一致（有后缀白名单） |
| 3 | `GET /api/status` | `{ok,device:{...},rates,version,signal_present,capture_dir}` | 顶层**还多一个 `occupied` 布尔字段**（501-504 行）；`device` 内含 present/initialized/endpoints/occupied，出错时另有 `error` 字符串 | **差异：顶层多 `occupied`** |
| 4 | `POST /api/capture` | 入参 `{rate_hz,seconds}`；出参含 achievement/saved_path | 完全一致；`seconds` 有默认值 1.0；achievement 分母用 `seconds*hz`（已修正口径） | 一致 |
| 5 | `GET /api/data/<id>` | octet-stream | 一致，且**额外带 `X-Rate-Hz`、`X-Samples` 响应头** | 差异：清单漏记响应头 |
| 6 | `POST /api/capture/triggered` | 同 capture + found/trigger_offset | 一致；trigger 类型 edge/rising/falling/level/pulse；多 `pre_ratio` 校验 | 一致 |
| 7 | `POST /api/decode` | `{ok,events:[{kind,start_sample,end_sample,data}],summary,count}` | 一致；`data` 非 dict 时包成 `{"value":...}`；`summary` 是 `kind×n` 聚合串 | 一致 |
| 8 | `GET /api/measure/<id>?window=[s,e]` | `{ok,channels:[{channel,edges,freq,duty,high_ratio,min_pulse,max_pulse}]}` | 一致，**且响应多 `n_samples` 字段**；`channels` 固定 8 项（`range(8)`），无通道筛选 | **差异：多 `n_samples`、固定 8 通道** |
| 9 | `POST /api/save` | format csv/vcd/bin | 一致；扩展名映射写死 3 种；空文件二次校验 | 一致 |
| 10 | `GET /api/open-folder` | `{ok,path}` | 一致；Windows 调 `explorer` | 一致 |
| 11 | `GET /api/events` | SSE 进度流 | 一致；先发 hello，1s 心跳 `: ping`，120s 超时，队列上限 100 | 一致（有 120s 上限细节） |

补充差异（清单未覆盖的实现事实）：
- `safe_handler` 把**所有非 ApiError 异常统一转 400**（不是 500），消息为 `服务器内部错误：{e}`。
- `json_body` 请求体硬上限 **8 MB**；响应体**无上限**。
- 路由未匹配时 GET/POST 都返回 404，中文消息区分「页面或接口」与「接口」。
- `window` 解析用 `json.loads(query["window"][0])`，是 **JSON 数组字符串放 URL**（需 urlencode），不是多参数。

## 2. 现有能力缺口（≥6 条）

| # | 缺口 | 影响 | 建议 |
|---|------|------|------|
| 1 | `window` 只有 `measure` 支持，`decode` 吃全量 blob | 区间解码只能先解 4800 万样本再前端丢弃，白算 99% | `/api/decode` 加 `window`，解码前切片 |
| 2 | `/api/decode` 无分页/限流，3 万事件全量进 JSON | 单响应约 3.6 MB，前端 JSON.parse 30-80ms、内存翻倍，DOM 只显示 500 条 | 加 `limit/offset` 或窗口优先；返回 `total`+`truncated` |
| 3 | 409 不细分「设备忙 / 被占用 / 未初始化 / 缺端点」 | 前端只能靠中文字符串猜，无法自动重试或给精确引导 | 引入 `code` 子码：`BUSY/OCCUPIED/NOT_READY/NO_DEVICE` |
| 4 | `register` 超 20 条用 `popitem` 丢元数据，但**不删磁盘文件** | 每次 48 MB，采 20 次后老文件永久滞留，磁盘无界增长 | 加配额上限 + 过期清理，或提供删除接口 |
| 5 | 无采集历史列表 API | 前端只靠 SSE `done` 事件记住 id，刷新后丢失上下文 | 新增 `GET /api/history` / `GET /api/sessions` |
| 6 | 无「会话」实体：AB 点、窗口、解码参数无法持久化 | 用户关页即失，无法复现/对比 | 会话保存/加载 API，落盘 JSON manifest |
| 7 | `measure` 固定算 8 通道，无法只算选中通道 | 小区间也要 8 通道各跑一遍向量化，浪费 ~8× | 加 `channels` 数组筛选参数 |
| 8 | 脉冲计数无明确语义 | `edges` 是边沿数、`freq` 是频率，都没有「完整周期数」 | `measure` 增 `cycles` 字段（上升沿对数） |
| 9 | `/api/save` 无 `.mat`，协议只 4 种 | MATLAB 用户无法直接分析；1-Wire/SWD/JTAG 解码不可用 | 扩展 format 与 protocol 注册表 |
| 10 | `read_capture` 每次全量 `read()` 48 MB 到内存，多请求并发叠加 | decode+measure+save 并发时可瞬时占用数百 MB | 只读可并发但需缓存/内存映射或排队 |

## 3. 新功能的前后端归属判断

数据量级以 48 MHz×1 s = **4800 万样本（48 MB）** 为基准。

| # | 功能 | 数据量级 | 前端算会怎样 | 结论 |
|---|------|---------|------------|------|
| 1 | 时间线刻度 | 只需起止样本+采样率，O(刻度数) | 瞬时，纯算术 | **前端** |
| 2 | AB 标记 | 仅 2 个样本索引 | 瞬时，纯 UI 状态 | **前端** |
| 3 | AB 区间统计 | 区间常见 1 千~10 万样本 | 小区间前端可算；全量 8 通道向量化前端 ~400-800ms 卡顿 | **都可以**（小区间前端即可，统一口径推荐后端 measure+window） |
| 4 | 区间内解码 | 解码算法重，事件可达 3 万 | 前端重写协议解析成本高、易错 | **后端**（decode 加 window） |
| 5 | 脉冲计数 | 区间内边沿扫描 | 小区间可算；需与统计口径一致 | **后端**（并入 measure，复用向量化） |
| 6 | 会话保存/加载 | manifest 几 KB + 引用文件 | 无持久化能力 | **后端** |
| 7 | 采集历史列表 | 元数据 20 条 + 磁盘文件 | 前端无文件枚举权限 | **后端** |
| 8 | 多会话对比 | 两路已解码/已统计数据 | 对比渲染在前端，数据由后端给 | **都可以**（数据后端、比对前端） |
| 9 | 更多协议解码 | 同 4 | 前端无解码器 | **后端**（新增解码模块） |
| 10 | 导出 MATLAB .mat | 48 MB 写文件 | 浏览器无法写本地指定路径 | **后端** |
| 11 | 导出 PNG 截图 | 已在 canvas 渲染 | `canvas.toDataURL` 零网络、零依赖 | **前端** |
| 12 | 自动测量历史 | 多次统计结果 | 需持久化与聚合 | **后端** |

## 4. 新增 API 规格

约定：所有响应都带 `ok:bool`；错误走 `safe_handler`/`ApiError`，格式 `{"ok":false,"error":"中文"}`。字段表列「字段|类型|必填|范围/说明」。

### 4.1 区间统计（验证现有 `window`，并增强）

`GET /api/measure/<id>?window=%5Bs%2Ce%5D[&channels=0,1]`

**现有 window 验证结论**（638-654 行）：基本正确——`json.loads` 解析 `[s,e]`、`int()` 转换、`start` clamp 到 `[0,N]`、`end` clamp 到 `[start,N]`，`end<start` 会退化为 `start`（返回空区间而非报错）。缺陷：① URL 必须是编码后的 JSON 数组；② 负值/越界静默截断不报错；③ 不回显实际生效的 `s/e`；④ 固定 8 通道。

请求（query）：

| 字段 | 类型 | 必填 | 范围/说明 |
|------|------|------|----------|
| `window` | JSON 数组字符串 | 否 | `[start,end]` 样本索引，0≤start≤end≤N；省略=全量 |
| `channels` | 逗号串 | 否 | 如 `0,2`，0..7；省略=全部 8 通道（**新增**） |

响应：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | bool | true |
| `channels` | array | 每项 `{channel,edges,cycles,freq,duty,high_ratio,min_pulse,max_pulse}`；`cycles` 为新增上升沿周期数 |
| `n_samples` | int | 实际参与统计的样本数（现有已有） |
| `window` | array | `[实际start,实际end]`（**新增回显**） |

错误码：400 `window 参数格式应为 [start,end]`（现有）/ `channels 必须是 0..7 的逗号分隔列表`（新增）；404 `找不到采集编号 {id}` / `采集文件已不存在`。数据量：8 通道×7 字段 < 2 KB。一致性：沿用现有路径与字段名，仅增可选参数与回显。

### 4.2 区间解码（改现有 `/api/decode`）

请求体在现有基础上加 `window`、`limit`、`offset`。

| 字段 | 类型 | 必填 | 范围/说明 |
|------|------|------|----------|
| `id` | string | 是 | 采集编号 |
| `protocol` | string | 否 | uart/i2c/spi/can，默认 uart |
| `params` | object | 否 | 协议参数，默认 `{}` |
| `window` | array[int,int] | 否 | **新增**，样本区间 `[s,e]`，先切 blob 再解码 |
| `limit` | int | 否 | **新增**，1..5000，默认 5000 |
| `offset` | int | 否 | **新增**，≥0，默认 0 |

响应：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok`/`events`/`summary`/`count` | — | 沿用现有 |
| `total` | int | **新增**，解码事件总数 |
| `truncated` | bool | **新增**，是否因 limit 截断 |

错误码：400 `window 必须是 [start,end] 且 0<=start<=end`、`limit 需在 1..5000`、`offset 不能为负`、`params 必须是对象`、`不支持的协议 {p}`；404 同 read_capture。数据量：`limit=5000` 时约 600 KB 上限，可控。实现依据：在 `handle_decode` 拿到 `blob` 后按 `window` 切片再调 `decode_events`，分页在事件列表序列化前做。

### 4.3 会话保存/加载

**POST /api/session/save**

| 字段 | 类型 | 必填 | 范围/说明 |
|------|------|------|----------|
| `name` | string | 是 | 1..64 字符 |
| `capture_id` | string | 是 | 引用已有采集编号 |
| `ab` | array[int,int] | 否 | AB 样本索引 |
| `protocol`/`params` | string/object | 否 | 保存时解码配置 |
| `notes` | string | 否 | ≤1000 字符 |

响应：`{ok, id, path, saved_at}`（id 为会话 id，复用 `STATE.next_id()` 风格）。错误：400 `name 不能为空`、`会话参数无效`；404 采集不存在；409 同名已存在（可选覆盖标志）。数据量 < 2 KB。落盘到 `CAPTURE_DIR/sessions/<id>.json`（新子目录，写入前 `os.makedirs`），**不改现有文件**。

**GET /api/session/load/<id>** 响应字段同保存请求 + `ok`、`id`、`capture_exists`：若引用的采集文件已丢失，`capture_exists=false` 但仍返回 manifest（提示用户重新采集）。错误：404 `找不到会话 {id}`。

### 4.4 会话列表

`GET /api/sessions` 响应：`{ok, sessions:[{id,name,capture_id,ab,saved_at}], total}`。按 `saved_at` 倒序。错误：400 `会话目录读取失败：{e}`。数据量：几十条 < 10 KB。实现：扫描 sessions 目录 JSON，读 name/时间，不读采集数据。

### 4.5 脉冲计数（并入 measure，不单列路由）

**结论：不新增独立路由**，在 `/api/measure` 增加可选 `mode=full|pulse` 与响应字段 `cycles`（见 4.1），理由：脉冲计数与边沿/占空比共享同一次 `bits` 向量化，拆路由会重复读 48 MB。`cycles = 上升沿数量`（`np.count_nonzero((bits[1:]==1)&(bits[:-1]==0))`），复用现有 `rising` 变量（255-256 行），零额外扫描。若需「完整高脉冲数」再返回 `high_pulses=len(high_runs)`。错误与数据量同 4.1。

### 4.6 导出 .mat（改现有 `/api/save`）

请求体加 `format:'mat'`，字段 `id` 必填、`channels` 可选。响应沿用 `{ok,path}`。错误：400 `format 只能是 csv、vcd、bin 或 mat`、`导出失败：{e}`（与现有同风格）。数据量：响应极小，文件约 48 MB。实现依据：`exporter.py` 现有 `export_csv/export_vcd/export_binary`，新增 `export_mat(path,data,rate,channels)`，用 `scipy.io.savemat`。**依赖风险**：`scipy` 未在现有 import 中出现，属新增依赖，需大脑授权；无依赖备选为 `numpy.savez`（非 .mat）或手写 MATLAB v5 头，均不推荐，建议确认 scipy 可用后再实现。

### 4.7 导出 PNG（前后端选择）

**结论：前端做**，`canvas.toBlob()`/`toDataURL()` 直接导出。理由：① 波形已在前端 canvas 渲染，后端无现成波形渲染能力（`09_app/wave_view.py` 是 PyQt 调试视图，非 Web 渲染）；② 后端渲染需引入 matplotlib/PIL 依赖并重画一遍，延迟与依赖成本都高；③ 前端导出零网络传输。后端无需新增路由。

## 5. API 一致性规范

- 命名：资源用复数/单数名词，动作体现在 HTTP 方法；路径小写、连字符分隔（沿用 `capture/triggered`、`open-folder`）。id 走 path，配置走 JSON body，过滤走 query（与 `window` 一致）。
- 错误格式：统一 `{"ok":false,"error":"中文"}`；业务错误 `ApiError(status,msg)`，其他异常由 `safe_handler` 转 400 `服务器内部错误：...`，禁止裸 500。
- HTTP 状态码：200 成功 / 400 参数或逻辑错误 / 403 禁止（静态穿越）/ 404 找不到资源 / 409 设备或状态冲突（建议加 `code` 子码）/ 500 预留（当前未用）。
- 成功响应必带 `ok:true`；列表必带 `total`；截断必带 `truncated`。
- 数值：样本索引 int，频率 float 保留 2 位，比率 round 6 位（对齐 `measure_channel`）。numpy 标量经 `json_default` 转 Python 原生类型。
- 请求体上限 8 MB（`json_body` 现有），大响应分页由服务端 `limit` 约束。
- 中文消息统一用「请…后重试 / 需在 X 到 Y 之间 / 找不到…」句式。

## 6. 性能与并发要点

- 6.1 区间统计耗时：`measure_channel` 对 4800 万样本逐通道做 `>>/`&`、`count_nonzero`、两次 `flatnonzero`、`median(diff)`，属 numpy 向量化但内存带宽密集（每通道读 ~48 MB 多次）。估全量 8 通道 **400-800 ms**；AB 小区间 10 万样本约 **1-3 ms**，快 **100-500 倍**。结论：区间优先在后端切完再算，收益巨大。
- 6.2 向量化确认：`measure_channel`（237-264 行）确为 numpy 向量化（`np.flatnonzero`/`np.count_nonzero`/`np.diff`/`np.median`），无 Python 逐样本循环；但 `handle_measure` 对通道是 Python `for` 循环（653 行），8 通道各调一次。
- 6.3 大响应体：3 万事件×约 120 B ≈ **3.6 MB**。方案：优先 `window` 缩范围；再 `limit/offset` 分页；`summary` 始终返回聚合便于前端显示总量。避免一次性把 3 万条塞进 DOM。
- 6.4 并发：`ThreadingHTTPServer` 多线程；`device_lock` 仅护采集，`meta_lock` 护 `captures`/`next_id`，`listener_lock` 护 SSE 队列。只读路由（data/decode/measure/save/sessions）**可并发**，但每次 `read_capture` 全量读 48 MB，多请求内存叠加；建议对 decode/measure 加共享缓存或限制同 id 并发数。新会话保存/加载涉及写文件，建议用独立 `session_lock`，不与 `device_lock` 争用。

## 7. 实现优先级与工作量估算

| API | 优先级 | 预计行数 | 依赖 |
|-----|--------|---------|------|
| 区间统计增强（channels/cycles/window 回显） | P0 | ~20 | 现有 measure_channel |
| 区间解码 + 分页（改 decode） | P0 | ~25 | 现有 decode_events |
| 历史/会话列表 `GET /api/sessions` | P1 | ~35 | sessions 目录约定 |
| 会话保存/加载 | P1 | ~80 | 新 JSON manifest 结构 |
| 脉冲计数（并入 measure） | P1 | ~10 | 复用 rising 变量 |
| 导出 .mat | P2 | ~25 | **scipy（需授权）** |
| 409 细分错误码 | P2 | ~15 | 前端配合 |
| 更多协议（1-Wire/SWD/JTAG） | P3 | 每协议 ~150+ | 新解码模块 |
| 导出 PNG | P1 | 0（前端） | canvas API |

## 8. 风险与注意事项

- `.mat` 需 scipy，属新增依赖；契约禁止擅自新增，须先获大脑授权，否则此 API 暂缓。
- 会话保存引用 `capture_id`，而采集元数据 20 条上限会 `popitem` 丢失 id；会话可能引用已过期采集，加载时须检查 `capture_exists` 并提示。
- 磁盘文件不随元数据淘汰而删除（缺口 4），会话与历史会放大该问题，建议同期设计清理策略。
- `window` 放在 URL，前端必须 `encodeURIComponent(JSON.stringify([s,e]))`，否则 `parse_qs` 解析异常。
- 改动现有 `/api/decode`、`/api/measure`、`/api/save` 必须向后兼容：新参数全部可选，默认行为不变。
- SSE 队列上限 100 且 120 s 超时，新增异步进度事件时注意不要撑爆队列。
- 本设计未改任何现有文件；落地时需独立批次实现，每批后跑现有测试（`09_app/test_*.py`）。
