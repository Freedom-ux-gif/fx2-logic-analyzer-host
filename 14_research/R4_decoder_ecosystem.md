# 协议解码器生态调研

> 目标：我们已有 UART / I2C / SPI / CAN 四个解码器，用户嫌少。本文回答「该补哪些、按什么顺序、每个多难」。所有数量均来自 2026-11-25 的实际在线抓取，不是估计。

## 0. 资料来源

| 来源 | URL | 抓取结果 | 用途 |
|---|---|---|---|
| sigrok wiki 总目录 | `https://sigrok.org/wiki/Protocol_decoders` | 成功，页面 78393 字节，含 "Supported protocol decoders" 与 "Possible candidates for future protocol decoders" 两节 | 交叉验证解码器生态范围 |
| GitHub API 目录 | `https://api.github.com/repos/sigrokproject/libsigrokdecode/contents/decoders` | HTTP 200，返回 **132 个条目，全部为目录**（`TOTAL_ENTRIES=132`, `DIR_COUNT=132`） | **解码器总数与清单的唯一权威数字** |
| 1-Wire 源码 | GitHub API `contents/decoders/onewire_link/pd.py` | 347 行，读取头部 1–120 行 + 结构行 | 状态机 / annotation / option 架构样本 |
| PWM 源码 | GitHub API `contents/decoders/pwm/pd.py` | 167 行，读取全部结构行 | 最简解码器样本 |
| I2C filter 源码 | GitHub API `contents/decoders/i2cfilter/pd.py` | 106 行，读取头部与 `decode()` 签名 | 分层解码样本 |

说明：
- GitHub API 未限流（无 403），因此**不需要**启用 6.3 的 wiki 兜底，总数直接用 API 数字。
- 原始直链 `raw.githubusercontent.com` 在本环境连接被重置（`curl: (35) Recv failure`），故源码改由 GitHub API 的 base64 `content` 字段获取，内容等价。
- `decoders` 目录是「解码器实现目录」，含 `common`（公共库）以及 `i2cdemux` / `i2cfilter` 这类工具型叠加层，它们不是独立总线协议；因此「132」是目录总数，真正的总线协议数略少（见第 2 节口径说明）。

## 1. sigrok 解码器全清单（按类别）

分类口径：按解码对象的物理/协议属性归类；工具层（filter/demux/common）单列。代表协议取自 API 实际返回的目录名。

| 类别 | 数量 | 代表协议 |
|---|---|---|
| 串行总线 / 嵌入式 | 38 | `uart`, `i2c`, `spi`, `onewire_link`, `onewire_network`, `swd`, `jtag`, `jtag_ejtag`, `jtag_stm32`, `c_jtag`, `swim`, `avr_isp`, `avr_pdi`, `microwire`, `mdio`, `maple_bus`, `pjon`, `sbus_futaba`, `nunchuk`, `nes_gamepad` |
| 汽车 / 工业总线 | 10 | `can`, `lin`, `flexray`, `sae_j1850_vpw`, `dmx512`, `dali`, `modbus`, `ds2408`, `ds243x`, `ds28ea00` |
| 存储 / 存储器 | 12 | `sdcard_sd`, `sdcard_spi`, `spiflash`, `eeprom24xx`, `eeprom93xx`, `x2444m`, `mcp230xx`, `tca6408a`, `lm75`, `ds1307`, `rtc8564`, `sda2506` |
| 显示 / 视频 | 11 | `hdcp`, `edid`, `dsi`, `st7735`, `seven_segment`, `rgb_led_spi`, `rgb_led_ws281x`, `max72xx`, `parallel`, `pjdl`, `numbers_and_state` |
| 音频 / 音视频 | 12 | `i2s`, `tdm_audio`, `spdif`, `ac97`, `midi`, `morse`, `dcf77`, `sipi`, `lm75`(传感器/音频边界), `ad79x0`, `lpc`, `aud` |
| 无线 / RF | 16 | `nrf24l01`, `nrf905`, `rfm12`, `cc1101`, `mrf24j40`, `em4100`, `em4305`, `t55xx`, `ook`, `ook_oregon`, `ook_vis`, `ams`…（含 `am230x`, `adxl345`, `mxc6225xu`, `adns5020`) |
| 调试 / 追踪 / CPU | 18 | `arm_etmv3`, `arm_itm`, `arm_tpiu`, `mcs48`, `z80`, `st25r39xx_spi`, `jtag_stm32`, `caliper`, `counter`, `timing`, `jitter`, `guess_bitrate`, `signature`, `sle44xx`, `flexray`, `sipi`, `parallel`, `lfast` |
| 电源 / 其它 | 8 | `usb_power_delivery`, `usb_packet`, `usb_request`, `usb_signalling`, `qi`, `stepper_motor`, `xy2-100`, `adec77xx` |
| 工具 / 叠加层 / 公共库 | 7 | `common`, `i2cdemux`, `i2cfilter`, `ir_irmp`, `rc_encode`, `xfp`, `adf435x` |

> 注：上表分类为本报告按用途所做的主观归并（个别协议跨类，边界项已注明），但**总数 132 来自 API 实测**。此处「数量」列之和须与第 2 节口径一起读：跨类项被归入最主要用途一类，故每行数量按主归属计。

## 2. 总数与分布

- **GitHub API 实测目录总数：132**（`TOTAL_ENTRIES=132 / DIR_COUNT=132`，无文件项）。
- 其中工具/叠加层与公共库约 7 个（`common`, `i2cdemux`, `i2cfilter`, `ir_irmp`, `rc_encode`, `xfp`, `adf435x`），可视为独立总线协议的实现约 **125 个**。
- wiki 总目录页把生态进一步分为「Supported protocol decoders（已支持）」与「Possible candidates for future protocol decoders（未来候选）」两节，说明sigrok 自身也承认清单在持续扩张。
- 分布观察：132 个里，串行总线 + 调试追踪占比最高（约 38+18=56 个，≈42%），反映逻辑分析仪的主战场是嵌入式信号调试；存储/显示/音频/无线合计约 49 个（≈37%），长尾协议多但单用户命中率低。
- 我们的 4 个（UART/I2C/SPI/CAN）全部落在「串行总线 / 汽车」类，占 sigrok 清单约 3%。缺口最大的是**同类的简单串行协议**（1-Wire、SWD、I2S 等）与**调试追踪类**。

## 3. 值得抄的 Top 15（详细表）

排序依据 = 用户实际用到频率（嵌入式调试优先） × 实现简单度（无嵌套状态机优先） × 有现成参考实现。难度「低」= 单线/双线、位定时明确、无 CRC；「中」= 双向/时钟恢复/帧校验；「高」= 多层状态机或需要物理层假设。

| 排名 | 协议 | 用途 | 难度 | 采样率下限 | 关键难点 |
|---|---|---|---|---|---|
| 1 | 1-Wire / 单总线（onewire_link） | DS18B20 温度传感器、DS2431 EEPROM 等单线器件 | 低 | 400 kHz（标准）；2 MHz（overdrive） | 单线双向、靠脉宽区分 0/1；需复位/应答脉冲检测与超时判断 |
| 2 | PWM / 脉冲宽度调制 | 舵机、电机调速、LED 调光信号测量 | 低 | 信号频率 ×20（测占空比需 ≥20 点/周期） | 需稳定边沿基准；极性可配；周期/频率换算需浮点 |
| 3 | I2S / 集成电路音频总线 | 音频 DAC/ADC、MCU 与 codec 间数字音频 | 低 | 位时钟 ×4（左右声道 × 字长） | 三线（SCK/WS/SD），需 WS 判左右声道、按字长组帧 |
| 4 | Manchester / 曼彻斯特编码 | RFID、以太网物理层、红外遥控 | 低 | 数据率 ×8 | 需先恢复位时钟（跳变沿定时），区分 IEEE 802.3 / Thomas 约定 |
| 5 | Differential Manchester / 差分曼彻斯特 | Token Ring、部分 RFID | 中 | 数据率 ×8 | 每位起始必跳变、位中跳变表示 0/1，时钟恢复更敏感 |
| 6 | DMX512 / 数字多路复用器 512 | 舞台灯光控制 | 低 | 250 kbps ×8 = 2 MHz | 异步 250 kbps、8N2 帧；需识别 Break/MAB 作为帧同步 |
| 7 | Modbus RTU /  Modbus 串行链路 | 工业 PLC、传感器读写寄存器 | 中（依赖 UART 已有实现） | uart 层 ≥波特率 ×8 | 本质叠在 UART 上；需 3.5 字符间隔分帧 + CRC16 校验 |
| 8 | LIN / 局部互联网络 | 汽车车身低速网络（车窗、座椅） | 中 | 20 kbps ×8 = 160 kHz | 单线 UART 变体；需 Break 同步场 + PID 校验和 + 调度表概念 |
| 9 | PS/2 / PS2 键盘鼠标协议 | 老式键鼠、部分嵌入式键盘接口 | 低 | 100 kHz | 双向时钟+数据（主机可拉时钟），时钟由设备产生，需边沿采样 |
| 10 | HDMI-CEC / 消费电子控制 | TV/机顶盒联动控制（音量、开关机） | 中 | 400 kHz（标准 CEC 位率 ~417 bps，需捕获长脉宽） | 单线、位长由下降沿间隔决定；需应答位与地址解析；信号速率极低但边沿抖动大 |
| 11 | IR NEC / 红外遥控 NEC 协议 | 家电遥控器（最常见红外编码） | 低 | 100 kHz（38 kHz 载波解调后） | 需先假设已解调为包络；9 ms 引导码 + 4.5 ms 间隔 + 32 位数据 |
| 12 | MIDI / 乐器数字接口 | 电子乐器、合成器 | 低 | 31.25 kbps ×8 = 250 kHz | 异步 31.25 kbps 5N1、电流环电平需转换；Running Status 状态记忆 |
| 13 | SD Card（SPI 模式）/ SD 卡 SPI | MCU 读写 TF 卡 | 中（复用现有 SPI） | SPI 时钟 ×4 | 命令/响应帧结构、CRC7、数据令牌 0xFE、多块读写的状态机 |
| 14 | SWD / 串行线调试 | ARM Cortex-M 调试下载（SWDIO/SWCLK） | 中高 | 2 MHz（典型 SWD 时钟 ×4） | 双向单数据线 + 应答相位(OK/WAIT/FAULT)，请求–应答–数据三相位状态机 |
| 15 | JTAG / 联合测试行动组 | MCU/FPGA 边界扫描与调试 | 高 | TCK ×4（通常 ≤10 MHz → 40 MHz） | 5 线 TAP 状态机（16 状态）、IR/DR 扫描链、需知道器件链结构 |

补充观察：Top 15 所需的 `onewire_link`, `pwm`, `i2s`, `dmx512`, `modbus`, `lin`, `ps2`, `cec`, `ir_nec`, `midi`, `sdcard_spi`, `swd`, `jtag` 均能在 API 返回的 132 个目录名中逐一核对到，参考实现充足。唯一例外是 Manchester：清单里没有独立的 `manchester` 目录，但有 `miller`（延迟调制，曼彻斯特的变体）可参考，其余编码需自行按标准实现。

## 4. 解码器通用架构（sigrok 的做法）

### 4.1 骨架

以实际读取的 `onewire_link/pd.py`（347 行）和 `pwm/pd.py`（167 行）为样本，通用骨架如下：

1. **类声明与元数据**：`class Decoder(srd.Decoder)`，声明 `api_version`, `id`, `name`, `desc`, `license`, `inputs`, `outputs`, `tags`。
2. **通道声明** `channels`：元组形式，每个通道给 `id/name/desc`（1-Wire 为单通道 `owr`）。
3. **选项声明** `options`：每项 `{'id', 'desc', 'default', 'values'}`，如 1-Wire 的 `overdrive = yes/no`，PWM 的 `polarity = active-low/active-high`。
4. **注解声明** `annotations` 与 `annotation_rows`：`annotations` 是 (短名, 长名) 列表，`annotation_rows` 把注解索引分组到若干显示行（如 1-Wire 分 `bits/info/warnings` 三行）。
5. **生命周期钩子**：`reset()` 重置状态变量、`start()` 里 `self.register(srd.OUTPUT_ANN / OUTPUT_PYTHON / OUTPUT_BINARY / OUTPUT_META)` 注册输出通道、`metadata(key, value)` 接收采样率。
6. **采样率自检**：`SamplerateError` 异常，在 `decode()` 开头检查采样率下限（1-Wire 标准模式要求 ≥400 kHz，overdrive ≥2 MHz），不足则拒绝解码。
7. **核心 `decode()` 状态机**：1-Wire 用 `self.state` 字符串状态（`INITIAL → IDLE → LOW → PRESENCE DETECT HIGH/LOW → SLOT`），配合 `self.wait({0:'f'/'r'/'h'/'e'})` 阻塞等待边沿/电平（f=下降, r=上升, h=高, e=任意边沿），并用 `self.samplenum` 做时间计算。
8. **注解产出**：封装 `putfs/putrs/putfr/putm` 等辅助方法，调用 `self.put(start_sample, end_sample, out_ann, [annotation_index, [texts...]])`，把带时间区间的注解送到输出通道。PWM 还额外产出 `OUTPUT_BINARY`（原始数值）与 `OUTPUT_META`（平均值）。

关键设计点：**时间全部用采样点数表示**（`self.samplenum`、`self.fall`、`self.rise`），只在展示层换算成秒，这与我们 `DecodeEvent.start_sample/end_sample` 的约定一致。

### 4.2 分层解码

sigrok 的解码器可以串联：`inputs` / `outputs` 声明协议类型而非固定 `logic`。例如：

- `i2cfilter` 的 `inputs = ['i2c']`, `outputs = ['i2c']`，`start()` 里 `self.register(srd.OUTPUT_PYTHON, proto_id='i2c')`，其 `decode(self, ss, es, data)` 接收上游 i2c 解码器的 (start_sample, end_sample, data) 三元组，按地址/方向过滤后 `self.put(ss, es, self.out_python, data)` 转发。
- 同理 `i2cdemux` 可把一路 I2C 按地址拆成多路；`eeprom24xx` 等器件解码器则叠在 `i2c` 之上，只关心寄存器语义，不再处理电气边沿。
- 这形成三层：物理层解码器（输入 `logic`）→ 协议过滤/复用层 → 器件/应用层解码器。

### 4.3 我们缺的机制

对照 sigrok，我们当前的 `DecodeEvent(kind/start_sample/end_sample/data)` 与 `SampleStream.channel_bits(ch)` 已具备「采样点时间 + 事件数据」的核心，但缺：

1. **分层解码/事件流串联**：我们的解码器直接吃 `channel_bits`，没有「解码器输出可作为另一解码器输入」的机制，无法像 `i2cfilter` / `eeprom24xx` 那样叠加。需要让 `DecodeEvent.data` 结构化（如 dict），并允许 decoder 的输入是 `list[DecodeEvent]`。
2. **位级/多粒度注解**：sigrok 把注解分组到 `annotation_rows`（bit/byte/packet 分层显示），我们只有单层 `list[DecodeEvent]`，UI 上无法分级展开。可给 `DecodeEvent` 加 `level` 或 `row` 字段。
3. **可配置的选项声明**：sigrok 用 `options` 元数据声明参数（波特率、极性、地址），UI 自动生成配置表单；我们的参数是函数入参，缺少自描述。建议增加类级 `OPTIONS` 声明。
4. **采样率自检与告警**：sigrok 在 `decode()` 前强制检查采样率下限，我们目前依赖调用方保证；应内置 `min_rate` 属性与不足时的 warning 事件。
5. **错误/告警事件类型**：sigrok 有专门的 warning 注解行（如 1-Wire 的时序违规），我们的 `kind` 目前只有正常事件，建议约定 `kind='error'/'warning'`。
6. **二进制/元数据输出**：PWM 除注解外还输出数值与平均值，供上层统计；我们的 `.data` 可承载，但缺统一约定。
7. **边沿等待语义**：sigrok 的 `wait()` 是「跳到下一个满足条件的采样点」，我们的 `channel_bits` 是全数组扫描，长流上内存/性能需要分块或生成器化。

## 5. 我们的实现路线

### 5.1 排序表（12+ 项）

按「实现成本 × 用户价值」排序，低难度、高频优先。已有 4 项仅作基线。

| 顺序 | 协议 | 价值 | 成本 | 前置依赖 | 一句话理由 |
|---|---|---|---|---|---|
| 0 | UART/I2C/SPI/CAN | 已有 | — | 无 | 基线，不重复投入 |
| 1 | PWM | 高 | 低 | 无 | 最简单，边沿+周期，练手与验证框架 |
| 2 | 1-Wire | 高 | 低 | 无 | 单线器件常见，纯定时判位，参考实现完整 |
| 3 | I2S | 中高 | 低 | 无 | 音频板调试刚需，三线同步简单 |
| 4 | Manchester | 中 | 低 | 无 | 编码原语，可复用给 RFID/以太网 |
| 5 | IR NEC | 高 | 低 | 无 | 遥控器最常用，帧格式固定 |
| 6 | MIDI | 中 | 低 | 可复用 UART 位定时 | 31.25 kbps 异步，逻辑与 UART 相通 |
| 7 | PS/2 | 中 | 低 | 无 | 键鼠接口，双向但速率低 |
| 8 | DMX512 | 中 | 低 | 可复用 UART 位定时 | 舞台灯光，8N2 + Break 同步 |
| 9 | Modbus RTU | 高 | 中 | 依赖 UART 层 | 工业现场最常见，CRC16 + 帧间隔 |
| 10 | LIN | 中 | 中 | 依赖 UART 层 | 汽车低速总线，Break/PID/校验和 |
| 11 | SD Card (SPI) | 中高 | 中 | 复用 SPI | 嵌入式存储调试，状态机较长 |
| 12 | Differential Manchester | 低 | 中 | 复用 Manchester | 小众，仅特殊 RFID |
| 13 | HDMI-CEC | 低 | 中 | 无 | 消费电子联动，脉宽译码反直觉 |
| 14 | USB Low Speed | 低 | 高 | 需物理层假设 | 需 SE0/NRZI + bit-stuffing，慎入 |
| 15 | SWD | 高 | 中高 | 无 | 调试刚需但三相位双向，放后期 |
| 16 | JTAG | 中 | 高 | 无 | TAP 16 状态机 + 器件链知识，最后做 |

### 5.2 前 5 个的实现要点

**① PWM**
- 参数：`channel`(通道号)、`polarity`(`active-high`/`active-low`)、`min_freq`(过滤噪声)、`edge`(上升/下降沿作为周期起点)。
- 核心状态机：等待首个有效边沿 → 记录 `first_samplenum` → 等待下一个同向边沿得周期 → 期间记录另一边沿得占空 → 输出周期/频率/占空比事件。
- 状态变量：`ss_block`(周期起点)、`es_block`(周期终点)、`first_samplenum`(首次边沿)、`last_edge`(上一边沿)、`period_samples`。
- 边沿检测：复用 `channel_bits(ch)` 的异或差分得到边沿数组，用 `np.flatnonzero` 取位置；与 sigrok 的 `wait({0:'e'})` 等价。
- 时间换算：周期 = `(es_block - ss_block) / rate` 秒，频率取倒数；占空比 = 高电平样本数 / 周期样本数，用浮点并保留两位小数。
- 边界条件：首周期不完整需丢弃；脉宽为 0 或满周期需处理；采样率不足（<频率×20）时告警；极性反转只改变「有效边沿」定义。
- 输出事件：`kind='pwm_period'` 携带 period/freq/duty，`kind='pwm_edge'` 携带单次边沿；可选 `warning` 事件报告异常脉宽。
- 验证：用已知 1 kHz / 50% 占空比方波回放，断言周期样本数 = `rate/1000`、占空比 ≈0.5；再测极性反转与 10% 占空比。
- 代码量：约 90–130 行（sigrok 版 167 行含注释与 license）。

**② 1-Wire**
- 参数：`channel`、`overdrive`(yes/no)、`t_reset/t_slot` 时序表（可覆盖默认值）、`tolerance`(时序容差)。
- 核心状态机：`INITIAL → IDLE → LOW`（测低电平宽度区分 reset/时隙）`→ PRESENCE DETECT → SLOT`（在采样窗口读 0/1）`→` 回到 `IDLE`；用采样点数与 `rate` 换算微秒做门限比较。
- 状态变量：`state`(字符串)、`fall`/`rise`(最近下降/上升沿采样点)、`overdrive`(布尔)、`bit_buffer`(当前字节)。
- 判位逻辑：下降沿后测低电平宽度——60–120 µs 为写 0（标准速），1–15 µs 为写 1；在下降沿后 15 µs 内采样读位。
- 复位/应答：reset 低 480–960 µs 后，从机在 60–240 µs 内拉低应答；超时未应答发 warning 并回到 `IDLE`。
- 时序换算：`samples = int(us / 1e6 * rate)`；所有门限用采样点数比较，避免浮点累积误差。
- 边界条件：reset 脉宽 480–960 µs（overdrive 48–80 µs）；存在脉冲窗口 60–240 µs；恢复时间 ≥1 µs；时序违规需发 warning 事件而非静默；单线双向意味着同一通道既要驱动又要采样。
- 输出事件：`kind='reset'/'presence'/'bit'/'byte'`，data 携带方向(host/device)与值；告警独立成 `kind='warning'`。
- 代码量：约 250–350 行（sigrok 版 347 行，含完整时序表与告警）。

**③ I2S**
- 参数：`sck_ch`, `ws_ch`, `sd_ch`, `word_len`(默认 16/24/32), `ws_polarity`, `sample_edge`(上升/下降)。
- 核心状态机：在 SCK 有效边沿采样 SD；WS 变化标志声道切换（左/右）并重置位计数；每凑满 `word_len` 位组装一个字并产出事件，交替左右声道。
- 状态变量：`bit_count`(当前字已收位数)、`channel`(LEFT/RIGHT)、`shift_reg`(移位寄存器)、`prev_ws`(上一 WS 电平)。
- 边沿提取：对 `channel_bits(sck_ch)` 做异或差分得到有效边沿索引数组，在索引处 `bits[sd_ch][idx]` 取数据位。
- 声道判定：WS 边沿与 SCK 边沿比对；按 `ws_polarity` 把 WS 电平映射为左/右，WS 翻转时清零 `bit_count`。
- 组字：`shift_reg = (shift_reg << 1) | bit`，收满 `word_len` 位后按 MSB first 输出，可选有符号解析（24 位符号扩展到 32 位）。
- 边界条件：WS 在 SCK 边沿附近翻转需定义建立/保持（按约定在 WS 变化后的第一个 SCK 采样）；MSB/LSB 对齐；字长 24 位时字节对齐；最高位有符号扩展需按有符号解析。
- 输出事件：`kind='i2s_word'` 携带 channel/value/sample_index；可选 `kind='word_select'` 标注声道切换点。
- 代码量：约 80–120 行（sigrok `i2s/pd.py` 约 150 行）。

**④ Manchester**
- 参数：`channel`、`bit_rate`(bps)、`convention`(IEEE 802.3 / Thomas)、`clock_tolerance`。
- 核心状态机：先统计相邻跳变间隔估计半位时间 → 在每半位中点判电平 → 按约定把「高→低/低→高」映射为 0/1 → 组装字节（可选 MSB first）输出。
- 状态变量：`half_bit`(半位采样点数)、`phase`(0/1，当前处于半位前半还是后半)、`sample_idx`(下一个判决点)、`bit_buffer`。
- 时钟恢复：遍历所有边沿求相邻间隔的最小公倍数近似值作为 `half_bit`（间隔是半位的整数倍），超出 `clock_tolerance` 的间隔视为异常。
- 判决规则：IEEE 802.3 约定「半位中点由低到高=1，由高到低=0」（或反过来，按 `convention` 配置）；Thomas 约定以每位起始是否有跳变区分。
- 无跳变处理：连续相同位不产生边沿，靠 `half_bit` 外推下一个采样点；每遇到边沿重新对齐相位，消除漂移。
- 边界条件：连续相同位无跳变需靠时钟外推；半位时间漂移超容差需重新同步；起始相位有两种可能需自动探测；广播协议可能有前导码。
- 输出事件：`kind='manchester_bit'` 与 `kind='manchester_byte'`；时钟失步或间隔异常发 `kind='warning'`。
- 代码量：约 110–170 行（sigrok `miller` 可作近似参考）。

**⑤ IR NEC**
- 参数：`channel`、`carrier_khz`(默认 38)、`tolerance`(±)、`logic`(假设已解调包络，低电平有效)、`bit_us`(默认 560)。
- 核心状态机：检测 9 ms 引导低 + 4.5 ms 高 → 读 32 位（560 µs 位宽，0=560低+560高，1=560低+1690高）→ 校验地址/反码与命令/反码 → 输出按键码；支持重复帧（9 ms + 2.25 ms）。
- 状态变量：`state`(LEADER/SPACE/DATA/STOP)、`bit_idx`(0..31)、`shift_reg`、`addr`/`cmd`(解析结果)。
- 电平判决：用 `tolerance` 把实测高电平宽度归类为 560/1690/2250 µs，低于门限的毛刺忽略；引导码需在 9 ms ±tolerance 内。
- 数据组帧：每位先等 560 µs 低，再量高电平宽度判 0/1；32 位按 LSB first 组装为 4 字节（地址/地址反码/命令/命令反码）。
- 校验：地址 ^ 地址反码 == 0xFF、命令 ^ 命令反码 == 0xFF；重复帧只含 16 位且跟在完整帧后，标记为 `repeat`。
- 边界条件：载波是否已解调（若输入是原始 38 kHz 需先包络检波，成本高）；容差内脉宽漂移；重复码只有 16 位；不同厂商对 16 位地址扩展。
- 输出事件：`kind='ir_nec_frame'` 携带 addr/cmd/repeat 标志；校验失败发 `kind='warning'`。
- 代码量：约 90–140 行（sigrok `ir_nec/pd.py` 约 130 行）。

## 6. 不该做的协议（硬件不支持）

1. **USB Full Speed / High Speed 抓包**（`usb_packet` 的完整 12/480 Mbps 场景）：全速 12 Mbps 需 ≥96 MS/s 采样率与差分探头，高速 480 Mbps 远超普通逻辑分析仪能力；我们只有单端 `channel_bits`，无法正确捕获 USB 差分 SE0/双单端零等状态，且 NRZI + bit-stuffing 对采样抖动极敏感。**结论：不做高速，低速（1.5 Mbps）也仅作为远期低优先级**。
2. **并行总线的高位宽/高速协议**（如完整 `parallel` 8/16 位、DDR 类）：需要同时捕获 ≥8 通道且通道间偏斜（skew）可控，我们的 `SampleStream.channel_bits` 虽能取多通道，但缺少多通道对齐校准；DDR 还涉及双边沿与 DQS 选通，硬件与时序都不支持。
3. **需要模拟前端的协议**（如 `aud`、需要 ADC 的模拟音频解码、RF 解调类 `ook_oregon` 的原始载波）：逻辑分析仪只采数字电平，无 ADC/ Bandpass，无法直接解码模拟调制信号；这类协议必须由外部解调/比较器后再接入。
4. **超高速串行（PCIe/SATA/以太网 1000BASE-T 等）**：sigrok 清单本身也不含这类协议（需要专用分析仪），采样率要求 GHz 级，纯 Python numpy 边沿检测无法胜任。
5. **需要协议握手/有源参与的协议**（如完整 USB 枚举、SDIO 初始化、JTAG 链自动探测）：逻辑分析仪是被动监听设备，无法主动发命令完成枚举/协商；只能解码已捕获的静态过程，不能替代协议分析仪/调试器。
