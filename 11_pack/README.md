# 逻辑分析仪采集库 —— 使用与开发说明

把采集后端封装成稳定、可复用、能打包成 exe 的库。全中文界面，面向不懂命令行的用户。

## 给用户：怎么用

1. **先自检**：双击 `selfcheck.py`（或命令行 `python -I selfcheck.py`）。看到全部 `[OK]` 就可以采集。
   - 如果提示"请先启动一次 Logic.exe"，照做一次：启动官方 Logic 软件、识别到设备后关闭，再重试自检。
2. **图形界面**：双击 `guitest_app.py`（或命令行 `python -I guitest_app.py`）。选采样率、填时长，点【开始采集】，中部画 8 路波形，底部显示中文结果。
3. **双击 exe**：运行 `dist\LogicScope.exe` 即可打开界面，不需要装 Python。
   - exe 由 `make_exe.py` 生成；想换中文名，把脚本里 `NAME = "LogicScope"` 改成 `"逻辑分析仪"` 再重跑（中文名在个别机器上可能出问题，故默认英文名）。

每次采集的原始数据会自动存到系统临时目录 `logic_capture_<时间戳>.bin`，即使 exe 出错也不会丢。

## 给开发者：协议要点（全部实测确认）

1. **必须先跑一次 Logic.exe 初始化**（实测确认）：端点从 `0x01 0x81 0x02 0x04 0x86 0x88` 变为 `0x01 0x81 0x82 0x06`（alt setting 0）。没有 0x82 就没法采。
2. **命令必须加密**（实测确认）：明文 `{0x01, delay}` 写入成功但设备不出数据；经 `obfuscate()` 加密后才出数据。
3. **delay = 48000000/rate − 1**（实测确认）：200kHz 时 = 0xEF；4MHz 时 = 11。
4. **通道映射 CHn → bitn**（实测确认）：CH0=bit0 … CH7=bit7，与 sigrok 文档相反。
5. **端点定义**（实测确认）：数据端点 0x82，命令端点 0x01，应答端点 0x81。

## 性能实测数据

用 `capture_timed(n_readers=3)` 测得，2 秒采集：

| 采样率 | 样本数 | 实际时长 | 实测速率 | 达成率 |
|---|---|---|---|---|
| 4 MHz  | 8,192,000 B  | 2.031s | 4.03M samples/s | 100.8% |
| 8 MHz  | 16,187,392 B | 2.015s | 8.03M samples/s | 100.4% |
| 12 MHz | 24,182,784 B | 2.010s | 12.03M samples/s | 100.3% |
| 24 MHz | 48,168,960 B | 2.004s | 24.04M samples/s | 100.1% |

**结论**：3 个读线程 + 64KB 缓冲可全速跑满 24MHz（24 MB/s）。不需要异步 API。

## 已知限制

- 24MHz 高负载时 Python 侧可能跟不上：实测虽满速，但 CPU 占用高。
- 未做触发采集：目前是"开始后连续采集 N 秒"，不支持边沿触发/协议触发。
- 设备只允许一个进程独占打开；`LogicDevice` 用共享句柄+模块级采集锁保证库内部安全，但不能与 Logic.exe 同时抓。
- 达成率按"实际样本 / 标称速率 × 时长"计算；库会裁掉后端 FIFO 尾数，使样本数与时长对齐。

## 文件清单

- `logic_core.py` —— 采集核心库（LogicDevice / CaptureResult）
- `selfcheck.py` —— 环境与设备自检
- `guitest_app.py` —— 最小可用 GUI，支持 `--version` / `--selftest`
- `test_core.py` —— unittest 自测（6 个用例）
- `make_exe.py` —— PyInstaller 打包 + 冒烟测试（已带 `--hidden-import ctypes.wintypes` 修复冻结环境的 ctypes 裁剪问题）

## packaging 备注

- exe 为 onefile，首次启动会解包到临时 `_MEIPASS` 目录；`logic_core.py` 会自动把其中 `08_fx2/`、`03_host/` 加入模块搜索路径。
- 冒烟测试 `exe --version` 与真实采集 `exe --selftest` 均已实测通过，且无残留读线程/设备句柄。
- 临时原始数据在 `%TEMP%\logic_capture_<时间戳>.bin`。
