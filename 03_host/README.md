# Saleae 逻辑分析仪 —— 自研 USB 底层库（03_host）

纯 `ctypes` + WinUSB 实现，不依赖 pyusb / libusb / 官方 SDK。全中文注释与文档。

## 架构

```
  probe.py          （探测与自检：枚举、查速度、GET_DESCRIPTOR）
     │
     ▼
  winusb.py         （本库：ctypes 结构体、函数声明、SaleaeDevice 类）
     │
     ▼
  setupapi.dll  ── 枚举设备接口（SetupDiGetClassDevsW 等）
  winusb.dll    ── 实际收发（WinUsb_Initialize / ControlTransfer / ReadPipe / WritePipe）
  Kernel32      ── CreateFileW / CloseHandle
     │
     ▼
  设备（USB）
  inf_guid.py       （从本机 Saleae.inf 实读 7 个 DeviceInterfaceGUID，供上面两步使用）
```

## 为什么不用 pyusb

本机没有 libusb，且 Saleae 装的是 WinUSB 驱动（`Saleae.inf` 里 7 个设备节全是
`AddService=WinUSB`），走系统原生 WinUSB 更直接、零第三方依赖。

## API 对照表

已实现（WinUSB 函数 ↔ 本库方法 ↔ 用途）：

| WinUSB 函数 | 本库方法 | 用途 |
| --- | --- | --- |
| `WinUsb_Initialize` | `SaleaeDevice.open()` | 打开接口句柄 |
| `WinUsb_Free` | `SaleaeDevice.close()` | 释放接口句柄 |
| `WinUsb_QueryDeviceInformation` | `SaleaeDevice.open()` / `query_speed()` | 查 USB 速度（DEVICE_SPEED=0x01） |
| `WinUsb_ControlTransfer` | `SaleaeDevice.control_transfer()` | 发控制传输（如 GET_DESCRIPTOR） |
| `WinUsb_ReadPipe` | `SaleaeDevice.read_pipe()` | 从管道读数据 |
| `WinUsb_WritePipe` | `SaleaeDevice.write_pipe()` | 向管道写数据 |
| `WinUsb_SetPipePolicy` | `SaleaeDevice.set_pipe_policy()` | 设置管道策略（超时/RAW_IO 等） |
| `WinUsb_GetPipePolicy` | `SaleaeDevice.get_pipe_policy()` | 读取管道策略 |
| `WinUsb_AbortPipe` | `SaleaeDevice.abort_pipe()` | 中止管道传输 |
| `WinUsb_ResetPipe` | `SaleaeDevice.reset_pipe()` | 复位管道 |
| `WinUsb_FlushPipe` | `SaleaeDevice.flush_pipe()` | 冲洗管道 |
| SetupAPI `SetupDiGetClassDevsW` 等 | `enumerate_devices()` | 按 GUID 枚举设备、解析 VID/PID |
| Kernel32 `CreateFileW` / `CloseHandle` | `SaleaeDevice.open()` / `close()` | 打开/关闭设备路径 |

未实现（写清原因，不假装实现）：

| 功能 | 原因 |
| --- | --- |
| 管道信息查询（`WinUsb_QueryPipe` / `PIPE_INFORMATION`） | 有效 pipeId 依赖 `02_usb` 抓包结果，尚未确认数据管道端点号；避免硬编码错误端点，`probe.py` 明确输出「未实现 + 原因」。 |
| overlapped 异步 I/O | 同步模式（`Overlapped=None`）足够先跑通，未实现异步回调/事件等待。 |
| 内部 IOCTL（`IOCTL_WINUSB_*`） | 这些控制码不在公开的 `winusb.h` / `winusbio.h` 中，且 `Logic.exe` 导入表无 `DeviceIoControl`；本库只用公开的 `WinUsb_*` 导出，IOCTL 常量仅作推导记录供抓包对账。 |

## 下一步（早期遗留：这些「未知量」后来已解决）

> **现状说明**：本节写于项目早期。下面 3 个问题在后续工作中都已经找到答案（采样率通过加密管道命令下发、数据走 EP `0x82`、无需下载比特流）。这里保留原文，是因为它能说明**当时卡在哪里**；如果你只想看结论，直接读 [`交接手册/H1_硬件与协议.md`](../交接手册/H1_硬件与协议.md)。
>
> 本文件的原始依据来自原作者对原厂软件的抓包记录（`02_usb` 目录，**未随本仓库分发**）。

1. 采样率是如何下发的？（控制传输的 request/value 编码，还是走管道写寄存器？）
2. 采样数据走哪个 pipeId？（IN 端点号与传输类型是什么？）
3. 是否需要先加载 FPGA 比特流才能开始采样？（加载时机与通道是什么？）

## 已知限制

1. 本机设备未插入，无法做真实收发验证；已验证的是「代码正确、API 真实存在、无设备时给出明确错误而非崩溃」。
2. `probe.py` 无设备时退出码为 2，有设备且探测完成为 0，绝不因未捕获异常退出 1。
3. overlapped 异步 I/O 未实现（同步模式足够先跑通）。
4. `winusb.py` 中 `IOCTL_WINUSB_*` 的 function 编号按 WinUSB 内部固定顺序 0–7 推导，仅作资料记录，实际通信不依赖它们。

## 快速验收

```bash
cd /e/demo/40_逆向工程/逻辑分析仪/03_host
python -I inf_guid.py     # 打印 7 个 GUID + 所在 INF 行号
python -I winusb.py       # 枚举结果 [] + GUID + sizeof（SETUP_PACKET=8）
python -I probe.py ; echo $?   # 无设备提示，退出码 2
```
