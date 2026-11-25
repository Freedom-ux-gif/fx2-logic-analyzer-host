# 09_app —— 自研上位机

纯 Python 实现，不依赖官方 SDK，不依赖 libusb，不需要 C++ 编译器。

## 模块

| 文件 | 作用 |
|---|---|
| `decoder_base.py` | 公共基础设施：`SampleStream`、`DecodeEvent`、`Decoder` 基类 |
| `decoder_uart.py` | UART 解码器（波特率/校验/停止位可配） |
| `decoder_i2c.py` | I2C 解码器（START/STOP/地址/ACK/重复起始） |
| `decoder_spi.py` | SPI 解码器（CPOL/CPHA/CS/MISO） |
| `synth.py` | 合成测试数据生成器（造已知波形） |
| `test_decoders.py` | 解码器自测（unittest） |
| `wave_view.py` | tkinter 波形查看器（缩放/平移/光标/降采样） |
| `exporter.py` | 导出 CSV / VCD / 原始二进制 |
| `test_view_export.py` | 查看器与导出模块自测 |

## 数据格式

采集到的原始数据是**每字节 8 通道**：

- **CH1 在最高位 bit7，CH8 在最低位 bit0**
- 采样率 10 档：24M / 16M / 12M / 8M / 4M / 2M / 1M / 500k / 250k / 200k Hz

> 该位序由 sigrok 文档 + 大脑实读确认，并由 `synth_square_wave` 生成方波、`channel_bits(1)` 断言验证（CH1 有跳变、CH2 恒 0）。

## 运行约定：所有脚本统一 `-I` + 显式 `sys.path.insert`

本目录所有入口脚本都用：

```bash
python -I test_decoders.py
```

`-I`（isolated mode）会**同时清空 CWD 和 `PYTHONPATH`**，所以脚本内部必须自己插路径：

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

这是**有意为之的隔离，不是缺陷**：`-I` 能防止脚本目录里被塞入 `json.py` / `socket.py`
这类同名文件劫持标准库。从外部调用模块时也要显式插路径：

```bash
python -I -c "import sys; sys.path.insert(0,'.'); import wave_view, exporter"
```

## 三个解码器

所有解码器都返回 `list[DecodeEvent]`；事件含 `start_sample` / `end_sample` /
`kind` / `data`。便捷函数 `decode_uart` / `decode_i2c` / `decode_spi` 可直接传原始
bytes。

### UART（`decoder_uart.py`）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `channel` | 1 | 信号所在通道（1..8） |
| `baud` | 115200 | 波特率 |
| `idle_high` | True | 空闲电平是否为高 |
| `data_bits` | 8 | 数据位宽（1..8） |
| `parity` | `'none'` | `'none'`/`'even'`/`'odd'` |
| `stop_bits` | 1 | 停止位个数 |

用法：`decode_uart(data, rate=1000000, channel=1, baud=9600)` → byte 事件
（`data={'value':72,'hex':'0x48','char':'H'}`）；校验/停止位错另有
`parity_error`/`framing_error`。

### I2C（`decoder_i2c.py`）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `scl_channel` | 1 | SCL 所在通道 |
| `sda_channel` | 2 | SDA 所在通道 |

用法：`decode_i2c(data, rate=1000000, scl_ch=1, sda_ch=2)` → 事件序列
`start/address/ack/data/ack/.../stop`；重复起始报 `repeat_start`。

### SPI（`decoder_spi.py`）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `sck_channel` | 1 | SCK 通道 |
| `mosi_channel` | 2 | MOSI 通道 |
| `miso_channel` | None | MISO 通道（可选） |
| `cs_channel` | None | CS 通道（可选，低有效） |
| `cpol` / `cpha` | 0 / 0 | 时钟极性/相位 |
| `bits` | 8 | 每 word 位数 |
| `msb_first` | True | 高位在前 |

用法：`decode_spi(data, rate=1000000, sck_ch=1, mosi_ch=2, cs_ch=3, cpol=0, cpha=0)`
→ `word` 事件（`data['value']`、`data['miso_word']`）。

## 用法

```bash
# 跑全部自测
python -I test_decoders.py
python -I test_view_export.py

# 打开波形查看器（内部用合成方波演示）
python -I wave_view.py

# 解码一段已采集的数据
python -I -c "
import sys; sys.path.insert(0,'.')
from decoder_base import SampleStream
from decoder_uart import decode_uart
data = open('wave.bin','rb').read()
for e in decode_uart(data, rate=1000000, channel=1, baud=9600):
    print(e)
"

# 导出
python -I -c "
import sys; sys.path.insert(0,'.')
import exporter
data = open('wave.bin','rb').read()
print('csv rows:', exporter.export_csv('out.csv', data, 1000000, mode='changes'))
print('vcd rows:', exporter.export_vcd('out.vcd', data, 1000000))
print('bin bytes:', exporter.export_binary('out.bin', data))
"
```

## 性能

24MHz × 8 通道 = 每秒 24 MB。全部代码路径都用 **numpy 向量化**，不做逐样本 Python 循环。

实测（100 万样本）：

| 操作 | 耗时 |
|---|---|
| 降采样到 1200 像素列 | ~1.6 ms |
| CSV 导出（changes 模式） | < 3 s |

## 已知限制

- **全部自测基于合成数据**，未在真实采集的数据上验证过（设备当时处于固件异常状态）
- I2C/SPI 的时钟极性假定为常见配置（模式 0/1 已用合成数据覆盖）
- 不支持 CAN / USB 等复杂协议
- 波形界面未做真人交互测试（无 GUI 自动化手段）

## 自测状态（诚实版）

全部 **9/9 通过**，每个结论都附可复现的具体数值：

| 模块 | 状态 | 证据（实际输出） |
|---|---|---|
| `decoder_uart` | ✅ | `synth_uart("Hello",9600)` → `[72,101,108,108,111]` |
| `decoder_uart` 高速 | ✅ | `synth_uart("Hi",115200)` @4MHz → `[72,105]` |
| `decoder_i2c` 地址 | ✅ | `addr=0x50, rw=0` → `address(0x50)` |
| `decoder_i2c` 数据 | ✅ | `data=[1,2]` → `[1,2]` |
| `decoder_spi` | ✅ | `words=[0xAA,0x55]` → `['0xaa','0x55']` |
| 通道位序 | ✅ | CH1 有跳变、CH2 恒 0 |
| `decimate_for_display` | ✅ | 100 万样本 → 1200 列，**1.9 ms** |
| `exporter` CSV | ✅ | changes 模式，1,000,001 行 |
| `exporter` VCD | ✅ | 2,000,031 行，含 `$timescale`/`$enddefinitions` |
| `exporter` binary | ✅ | 1,000,000 字节直通 |

**返工记录（值得记住的教训）**：首版 `test_decoders.py` 报「全部通过」，
但大脑独立复跑发现 **4 处实际错误**：

| 错误 | 根因 |
|---|---|
| UART `Hello` → `[72,89,139,189]` | 字节间游标推进错，`samples_per_bit` 被 int 截断导致累积漂移 |
| UART `Hi`@115200 → `[72]` | 同上，只解出 1 字节 |
| I2C data → `[0, 128]` | MSB 累加方向反（`0x01` 解成 `0x80`） |
| SPI 直接崩 | `synth_spi` 的 CS 数组没在 bit 循环里延长，长度 `{3,35}` |

**结论：不接受「ALL TESTS PASSED」这种笼统声明。**
凡是「自测通过」，必须附一条**外部可复现的具体数值**，
并且要有独立复跑——自己测自己写的代码，很容易测出"假绿"。



## 合成数据自测

```bash
python -I test_decoders.py
```

`-I` 是隔离模式（清空 CWD 与 PYTHONPATH），脚本内部已用 `sys.path.insert`
显式加入自身目录，因此直接运行即可。用 `synth.py` 先造已知内容的波形，
再用解码器反解并逐字段断言（UART `"Hello"` 五个字节、`"Hi"@115200`、
偶校验、坏帧、I2C 写/读/Sr、SPI 模式 0/1、通道位序）。

**为什么用合成数据**：设备当前处于异常状态（所有 pipe 报 err 87），
且用户已离线，任何设备操作都会失败；本任务不碰 USB、不启动 Logic.exe，
全部结论基于合成数据自测。

**本任务的教训**：首版自测虽打印「ALL TESTS PASSED」，但只断言了"能跑"
没断言"数值对"，被大脑独立复跑抓出 4 处实际错误（UART 字节游标漂移、
I2C 数据错位、SPI 合成器数组漏 extend）。此后所有断言都改为逐字节比对
具体期望值，并附外部可复现命令。
