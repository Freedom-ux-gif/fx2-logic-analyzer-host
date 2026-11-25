# 本机工具链清单

> 纯记录：本章所有命令均为只读实跑，**未安装任何软件或 Python 包**。环境：Windows 10 19045 x64，Git Bash。

## 1. 实跑命令与真实输出

### 1.1 `node -v`
```
v24.16.0
```

### 1.2 `python --version`
```
Python 3.14.3
```

### 1.3 `python -m pip list`（只摘相关包）
从 `python -m pip list` 中 grep `numpy|pandas|scipy|matplotlib|capstone|pefile|frida|frida-tools` 的实际输出：
```
capstone                                                5.0.9
frida                                                   17.23.3
frida-tools                                             14.11.0
matplotlib                                              3.11.0
matplotlib-inline                                       0.2.2
numpy                                                   2.5.0
pandas                                                  3.0.6
pefile                                                  2024.8.26
scipy                                                   1.18.1
```

### 1.4 `which 7z dumpbin gcc g++ cl cmake ninja objdump`（Git Bash）
```
7z         NOT FOUND
dumpbin    NOT FOUND
gcc        NOT FOUND
g++        NOT FOUND
cl         NOT FOUND
cmake      NOT FOUND
ninja      NOT FOUND
objdump    NOT FOUND
```
（注：这里的 `NOT FOUND` 是 `which` 无输出后由脚本补写；上述 8 个可执行文件均不在当前 PATH。）

### 1.5 管理员权限检查
命令：
```
powershell -NoProfile -Command "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')"
```
实际输出：
```
False
```
即当前会话**不是管理员**。

## 2. 工具 / 状态 / 版本 / 本项目用途 / 缺了怎么办

| 工具 | 状态 | 版本 | 本项目用途 | 缺了怎么办 |
|---|---|---|---|---|
| node | 已安装 | v24.16.0 | 运行 REA CLI（`dist/cli.js`、`scripts/rea.mjs`） | 无需处理 |
| python | 已安装 | 3.14.3 | 脚本化解析抓包数据、pcap 处理 | 无需处理 |
| numpy | 已安装 | 2.5.0 | 样本数组/波形数据处理 | 无需处理 |
| pandas | 已安装 | 3.0.6 | 抓包数据表格化对账 | 无需处理 |
| scipy | 已安装 | 1.18.1 | 信号处理/滤波 | 无需处理 |
| matplotlib | 已安装 | 3.11.0 | 波形/采样数据可视化 | 无需处理 |
| capstone | 已安装 | 5.0.9 | Python 侧反汇编补充（对未混淆 DLL） | 无需处理 |
| pefile | 已安装 | 2024.8.26 | 解析 PE 头/节区/导入表 | 无需处理 |
| frida / frida-tools | 已安装 | 17.23.3 / 14.11.0 | 运行时插桩/函数 hook（对未混淆 DLL 或抓包辅助） | 无需处理 |
| 7z | 未安装（PATH 中无） | — | 解压固件/抓包归档 | 用 Python `zipfile`/`tarfile` 或 Windows 自带解压 |
| dumpbin | 未安装（PATH 中无） | — | 查看 PE 导入导出表 | 用已装的 `pefile` 或 REA `inspect-pe-resources` |
| gcc / g++ / cl | 未安装（PATH 中无） | — | 编译自定义 Analyzer DLL | 见第 3 节缺口① |
| cmake / ninja | 未安装（PATH 中无） | — | 构建 C/C++ 工程 | 见第 3 节缺口① |
| objdump | 未安装（PATH 中无） | — | 反汇编/objdump 后端 | 用 capstone 或 REA 自带后端；注意 REA `inspect-with-objdump` 依赖本机 objdump |
| 管理员权限 | 不具备 | False | 安装内核驱动/系统级工具 | 见第 3 节缺口② |
| 反汇编 GUI（Ghidra / IDA） | 未安装 | — | 交互式静态逆向 | 见第 3 节缺口③ |

## 3. 当前不具备、且有影响的三项能力缺口

### 缺口① 无 C/C++ 编译器（gcc/g++/cl/cmake/ninja 全部缺失）
- 影响：无法编译自定义 Analyzer DLL（插件 ABI 为 `CreateAnalyzer`/`DestroyAnalyzer`/`GetAnalyzerName` 三个 C 入口）；无法用 Ghidra 以外的原生调试手段配合编译验证。[本机实读 + 推断，未验证]
- 绕过方案：本阶段只做抓包对账，不编译插件；若后续必须编译，再单独申请安装构建工具链（本次不安装）。

### 缺口② 无管理员权限（IsInRole('Administrators') = False）
- 影响：无法安装 USBPcap 内核驱动做 USB 抓包；无法安装 WinUSB 驱动给别人机器使用。[本机实读 + 推断，未验证]
- 绕过方案：优先用现有 WinUSB 环境在应用层抓取控制传输/bulk 数据（如已有抓包能力则复用）；需要内核级抓包时请大脑/用户申请提权后再操作。

### 缺口③ 无反汇编器 GUI（Ghidra / IDA 均未安装）
- 影响：缺少交互式静态逆向环境；`Logic.exe` 已混淆，本来也依赖运行时抓包而非静态反汇编，但分析未混淆的 `Analyzer.dll`/插件 DLL 时少一个顺手的工具。[本机实读 + 推断，未验证]
- 绕过方案：用已安装的 Python `capstone` + `pefile` 做脚本化静态分析，或用 REA 的字符串/函数/交叉引用工具做静态侧辅助；GUI 反汇编器按需另行申请安装（本次不安装）。

## 4. 记录边界

- 本章仅记录当前 PATH 与 Python 环境的可见状态；未做安装、未改环境变量、未改任何配置。[本机实读]
