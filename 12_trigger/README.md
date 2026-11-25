# 12_trigger —— 软件触发采集

本目录给自研上位机补上**软件触发采集**能力：不再盲采固定秒数，而是先采满一段内存、在内存里找到信号满足条件的那一刻，再裁出触发点前后的数据（含预触发）。全离线计算，不依赖设备触发寄存器。

## 文件

- `trigger.py`：五种触发条件，`find(data, rate) -> int | None`，全部 numpy 向量化。
- `triggered_capture.py`：`TriggeredCapture` 采集器 + `TriggerResult` 结果。
- `test_trigger.py`：unittest 自测（7 个合成用例 + 3 个真实设备/性能用例）。

## 触发器参数与示例

| 触发器 | 参数 | 含义 |
|---|---|---|
| `EdgeTrigger` | `channel, rising=True, count=1` | 第 count 个上升沿（rising=False 为下降沿） |
| `LevelTrigger` | `channel, level=1, count=1` | 连续 count 个样本等于 level 的起点 |
| `PulseWidthTrigger` | `channel, min_samples=None, max_samples=None, polarity='high'` | 高/低电平脉宽落在区间内的脉冲起点 |
| `PatternTrigger` | `pattern: str, channel_map: list[int]` | 多通道并行模式，如 `'1x0'`，x 为不关心 |
| `UartStartTrigger` | `channel, baud, rate` | 下降沿且半个 bit 后仍为低（UART 起始位） |

```python
from trigger import EdgeTrigger, LevelTrigger, PulseWidthTrigger, PatternTrigger, UartStartTrigger
t1 = EdgeTrigger(0, rising=True, count=3)                     # CH0 第 3 个上升沿
t2 = LevelTrigger(0, level=1, count=100)                      # CH0 连续 100 个高电平
t3 = PulseWidthTrigger(0, 50, 150, polarity='high')           # 脉宽 50~150 样本的高脉冲
t4 = PatternTrigger('1x0', [0, 1, 2])                         # CH0=1, CH2=0
t5 = UartStartTrigger(0, 9600, 4000000)                       # CH0 上的 UART 起始位
```

通道映射遵循本机实测：CHn → bitn（0..7）。空数据返回 None；通道越界、count≤0、pattern 与 channel_map 长度不符均抛中文 ValueError。

采集器用法：

```python
from trigger import EdgeTrigger
from triggered_capture import TriggeredCapture
cap = TriggeredCapture(dev, 4000000, EdgeTrigger(0, rising=True), 0.2)
r = cap.run(1.0, max_wait_seconds=None)   # 未找到可指定最长等待时间循环再采
```

`TriggerResult` 字段：`data`（裁剪后）、`trigger_index`（原始下标）、`trigger_offset`（裁剪后下标）、`pre_samples`、`post_samples`、`rate_hz`、`found`、`message`。

## 预触发原理

传统触发必须边采边判断，触发前的数据已经流走，所以拿不到触发前的波形。这里反过来：**先把整段时间一次性采进内存，再离线找触发点**。既然全部样本都已在内存里，触发点之前的样本自然也都在，只要从触发点往前切出 `pre_trigger_ratio` 比例的一段即可。开头一段是启动瞬态/残留数据，不参与触发判断，因此触发点总落在预触发余量之后，裁剪后 `trigger_offset / len(data)` 恰好等于该比例。

代价是必须先采到内存：24 MHz × 2 秒 = 48 MB，可接受。

## 为什么不硬件触发

**如实说明**：我们只逆向出了「设置采样率 + 启动采集」命令（见 `08_fx2/capture_verified.py` 的 `obfuscate` / `capture_timed`），**设备的触发寄存器协议没有逆出来**，所以无法让硬件在信号满足条件时才开始传输。软件触发受限于「必须先采到内存再找」，最长采集时长由内存容量决定（24 MHz × 2 秒 = 48 MB，可接受）；优点是触发条件随时可改、可组合，不需要重刷固件。

## 实测数据（2026-11-25，Python 3.14.3 / numpy 2.5.0）

- 1000 万样本 `EdgeTrigger` 查找：**0.025 秒**（要求 < 1 秒）。
- 4 MHz 采集 1 秒（CH0 接 50 kHz 方波）：`found True`，`trigger_index=838925`，`trigger_offset=838844`，裁剪后长度 `4194223`，比例 ≈ 0.199995（目标 0.2）。
- 真实波形上升沿验证：触发点前一样本为 0、触发点为 1。
- 全部 10 个用例通过：`python -I test_trigger.py` → `ALL TESTS PASSED (10 cases)`。

## 验收命令

```bash
cd 12_trigger && python -I test_trigger.py
python -I -c "import ast;[ast.parse(open(f,encoding='utf-8').read()) for f in ['trigger.py','triggered_capture.py','test_trigger.py']];print('syntax ok')"
```
