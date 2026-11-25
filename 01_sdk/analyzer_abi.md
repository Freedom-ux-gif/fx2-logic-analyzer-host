> 本文档为节选（原文 68 KB / 272 个符号完整索引未随仓库分发）。内容为符号名与接口约定的整理，不含原厂二进制内容。

# Saleae Analyzer SDK C++ ABI 复原说明

## ABI 总览

- 目标 `Analyzer.dll` 是 **x64 PE**、基于 **MSVC v140 运行时**、**无 RTTI**、导出 **272 个符号**——由导出表与插件 DLL 实读确认。
- 导出名为标准 MSVC 修饰名（未观察到名称混淆），其中以 `??0`/`??1`/`??4`/`??_` 开头的构造/析构/赋值/vftable 共 85 个，剩余 187 个为实际方法——由导出表与插件 DLL 实读确认。
- 插件 DLL 统一暴露三个 C 入口：`CreateAnalyzer` 返回 `Analyzer*`，`DestroyAnalyzer(Analyzer*)` 销毁实例，`GetAnalyzerName()` 返回 `const char*`——由导出表与插件 DLL 实读确认。
- 本机 `Analyzers` 目录实读共 **24 个**插件 DLL（本机实读，Analyzers 目录 DLL 计数），合计 1413 个导出符号；插件侧以 `I2CAnalyzer.dll` 为代表，共 60 个导出（58 个 C++ 修饰名 + 3 个 C 入口）——由导出表与插件 DLL 实读确认。

> 说明：参数类型、返回类型与 `this` 调用约定均未复原；下文一切签名仅保留方法名，类型信息一律以原始修饰名呈现，不作猜测。

## 类成员表

**本节职责列为按方法名推断，未经反汇编验证。**

下表按类分组，仅收录非构造/析构/赋值/vftable 的 187 个方法。`序号` 为导出序号。地址列已移除，本副本不含地址信息。

### AnalyzerResults（31 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
|---|---|---|---|
| AnalyzerResults::AddChannelBubblesWillAppearOn | `?AddChannelBubblesWillAppearOn@AnalyzerResults@@QEAAXAEBVChannel@@@Z` | 111 | 添加·ChannelBubblesWillAppearOn（按方法名推断） |
| AnalyzerResults::AddFrame | `?AddFrame@AnalyzerResults@@QEAA_KAEBVFrame@@@Z` | 114 | 添加·Frame（按方法名推断） |
| AnalyzerResults::AddMarker | `?AddMarker@AnalyzerResults@@QEAAX_KW4MarkerType@1@AEAVChannel@@@Z` | 116 | 添加·Marker（按方法名推断） |
| AnalyzerResults::AddPacketToTransaction | `?AddPacketToTransaction@AnalyzerResults@@QEAAX_K0@Z` | 118 | 添加·PacketToTransaction（按方法名推断） |
| AnalyzerResults::AddResultString | `?AddResultString@AnalyzerResults@@QEAAXPEBD00000@Z` | 119 | 添加·ResultString（按方法名推断） |
| AnalyzerResults::AddTabularText | `?AddTabularText@AnalyzerResults@@QEAAXPEBD00000@Z` | 120 | 添加·TabularText（按方法名推断） |
| AnalyzerResults::CancelExport | `?CancelExport@AnalyzerResults@@QEAAXXZ` | 131 | 取消·Export（按方法名推断） |
| AnalyzerResults::CancelPacketAndStartNewPacket | `?CancelPacketAndStartNewPacket@AnalyzerResults@@QEAAXXZ` | 132 | 取消·PacketAndStartNewPacket（按方法名推断） |
| AnalyzerResults::ClearResultStrings | `?ClearResultStrings@AnalyzerResults@@QEAAXXZ` | 136 | 清空·ResultStrings（按方法名推断） |
| AnalyzerResults::ClearTabularText | `?ClearTabularText@AnalyzerResults@@QEAAXXZ` | 137 | 清空·TabularText（按方法名推断） |
| AnalyzerResults::CommitPacketAndStartNewPacket | `?CommitPacketAndStartNewPacket@AnalyzerResults@@QEAA_KXZ` | 138 | 提交·PacketAndStartNewPacket（按方法名推断） |
| AnalyzerResults::CommitResults | `?CommitResults@AnalyzerResults@@QEAAXXZ` | 139 | 提交·Results（按方法名推断） |
| AnalyzerResults::DoBubblesAppearOnChannel | `?DoBubblesAppearOnChannel@AnalyzerResults@@QEAA_NAEAVChannel@@@Z` | 142 | 执行·BubblesAppearOnChannel（按方法名推断） |
| AnalyzerResults::DoMarkersAppearOnChannel | `?DoMarkersAppearOnChannel@AnalyzerResults@@QEAA_NAEAVChannel@@@Z` | 144 | 执行·MarkersAppearOnChannel（按方法名推断） |
| AnalyzerResults::GetFrame | `?GetFrame@AnalyzerResults@@QEAA?AVFrame@@_K@Z` | 170 | 读取·Frame（按方法名推断） |
| AnalyzerResults::GetFramesContainedInPacket | `?GetFramesContainedInPacket@AnalyzerResults@@QEAAX_KPEA_K1@Z` | 171 | 读取·FramesContainedInPacket（按方法名推断） |
| AnalyzerResults::GetFramesInRange | `?GetFramesInRange@AnalyzerResults@@QEAA_N_J0PEA_K1@Z` | 172 | 读取·FramesInRange（按方法名推断） |
| AnalyzerResults::GetMarker | `?GetMarker@AnalyzerResults@@QEAAXAEAVChannel@@_KPEAW4MarkerType@1@PEA_K@Z` | 181 | 读取·Marker（按方法名推断） |
| AnalyzerResults::GetMarkersInRange | `?GetMarkersInRange@AnalyzerResults@@QEAA_NAEAVChannel@@_J1PEA_K2@Z` | 182 | 读取·MarkersInRange（按方法名推断） |
| AnalyzerResults::GetNumFrames | `?GetNumFrames@AnalyzerResults@@QEAA_KXZ` | 187 | 读取·NumFrames（按方法名推断） |
| AnalyzerResults::GetNumMarkers | `?GetNumMarkers@AnalyzerResults@@QEAA_KAEAVChannel@@@Z` | 188 | 读取·NumMarkers（按方法名推断） |
| AnalyzerResults::GetNumPackets | `?GetNumPackets@AnalyzerResults@@QEAA_KXZ` | 189 | 读取·NumPackets（按方法名推断） |
| AnalyzerResults::GetPacketContainingFrame | `?GetPacketContainingFrame@AnalyzerResults@@QEAA_K_K@Z` | 194 | 读取·PacketContainingFrame（按方法名推断） |
| AnalyzerResults::GetPacketContainingFrameSequential | `?GetPacketContainingFrameSequential@AnalyzerResults@@QEAA_K_K@Z` | 195 | 读取·PacketContainingFrameSequential（按方法名推断） |
| AnalyzerResults::GetPacketsContainedInTransaction | `?GetPacketsContainedInTransaction@AnalyzerResults@@QEAAX_KPEAPEA_KPEA_K@Z` | 196 | 读取·PacketsContainedInTransaction（按方法名推断） |
| AnalyzerResults::GetProgress | `?GetProgress@AnalyzerResults@@QEAANXZ` | 198 | 读取·Progress（按方法名推断） |
| AnalyzerResults::GetResultStrings | `?GetResultStrings@AnalyzerResults@@QEAAXPEAPEAPEBDPEAI@Z` | 199 | 读取·ResultStrings（按方法名推断） |
| AnalyzerResults::GetSearchData | `?GetSearchData@AnalyzerResults@@QEAAXPEAPEAPEBDPEAI@Z` | 205 | 读取·SearchData（按方法名推断） |
| AnalyzerResults::GetTransactionContainingPacket | `?GetTransactionContainingPacket@AnalyzerResults@@QEAA_K_K@Z` | 216 | 读取·TransactionContainingPacket（按方法名推断） |
| AnalyzerResults::StartExportThread | `?StartExportThread@AnalyzerResults@@QEAAXPEBDW4DisplayBase@@I@Z` | 262 | 启动·ExportThread（按方法名推断） |
| AnalyzerResults::UpdateExportProgressAndCheckForCancel | `?UpdateExportProgressAndCheckForCancel@AnalyzerResults@@IEAA_N_K0@Z` | 270 | 更新·ExportProgressAndCheckForCancel（按方法名推断） |

### AnalyzerSettings（22 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
|---|---|---|---|
| AnalyzerSettings::AddChannel | `?AddChannel@AnalyzerSettings@@IEAAXAEAVChannel@@PEBD_N@Z` | 110 | 添加·Channel（按方法名推断） |
| AnalyzerSettings::AddExportExtension | `?AddExportExtension@AnalyzerSettings@@IEAAXIPEBD0@Z` | 112 | 添加·ExportExtension（按方法名推断） |
| AnalyzerSettings::AddExportOption | `?AddExportOption@AnalyzerSettings@@IEAAXIPEBD@Z` | 113 | 添加·ExportOption（按方法名推断） |
| AnalyzerSettings::AddInterface | `?AddInterface@AnalyzerSettings@@IEAAXPEAVAnalyzerSettingInterface@@@Z` | 115 | 添加·Interface（按方法名推断） |
| AnalyzerSettings::ClearChannels | `?ClearChannels@AnalyzerSettings@@IEAAXXZ` | 134 | 清空·Channels（按方法名推断） |
| AnalyzerSettings::GetAnalyzerDisplayBase | `?GetAnalyzerDisplayBase@AnalyzerSettings@@QEAA?AW4DisplayBase@@XZ` | 150 | 读取·AnalyzerDisplayBase（按方法名推断） |
| AnalyzerSettings::GetChannel | `?GetChannel@AnalyzerSettings@@QEAA?AVChannel@@IPEAPEBDPEA_N@Z` | 157 | 读取·Channel（按方法名推断） |
| AnalyzerSettings::GetChannelsCount | `?GetChannelsCount@AnalyzerSettings@@QEAAIXZ` | 160 | 读取·ChannelsCount（按方法名推断） |
| AnalyzerSettings::GetExportOption | `?GetExportOption@AnalyzerSettings@@QEAAXIPEAIPEAPEBD@Z` | 166 | 读取·ExportOption（按方法名推断） |
| AnalyzerSettings::GetExportOptionsCount | `?GetExportOptionsCount@AnalyzerSettings@@QEAAIXZ` | 167 | 读取·ExportOptionsCount（按方法名推断） |
| AnalyzerSettings::GetFileExtension | `?GetFileExtension@AnalyzerSettings@@QEAAXIIPEAPEBD0@Z` | 168 | 读取·FileExtension（按方法名推断） |
| AnalyzerSettings::GetFileExtensionCount | `?GetFileExtensionCount@AnalyzerSettings@@QEAAII@Z` | 169 | 读取·FileExtensionCount（按方法名推断） |
| AnalyzerSettings::GetPreferedAnalyzerStartingSample | `?GetPreferedAnalyzerStartingSample@AnalyzerSettings@@QEAA_JXZ` | 197 | 读取·PreferedAnalyzerStartingSample（按方法名推断） |
| AnalyzerSettings::GetSaveErrorMessage | `?GetSaveErrorMessage@AnalyzerSettings@@QEAAPEBDXZ` | 204 | 读取·SaveErrorMessage（按方法名推断） |
| AnalyzerSettings::GetSettingsInterface | `?GetSettingsInterface@AnalyzerSettings@@QEAAPEAVAnalyzerSettingInterface@@I@Z` | 207 | 读取·SettingsInterface（按方法名推断） |
| AnalyzerSettings::GetSettingsInterfacesCount | `?GetSettingsInterfacesCount@AnalyzerSettings@@QEAAIXZ` | 208 | 读取·SettingsInterfacesCount（按方法名推断） |
| AnalyzerSettings::GetUseSystemDisplayBase | `?GetUseSystemDisplayBase@AnalyzerSettings@@QEAA_NXZ` | 224 | 读取·UseSystemDisplayBase（按方法名推断） |
| AnalyzerSettings::SetAnalyzerDisplayBase | `?SetAnalyzerDisplayBase@AnalyzerSettings@@QEAAXW4DisplayBase@@@Z` | 238 | 设置·AnalyzerDisplayBase（按方法名推断） |
| AnalyzerSettings::SetErrorText | `?SetErrorText@AnalyzerSettings@@IEAAXPEBD@Z` | 244 | 设置·ErrorText（按方法名推断） |
| AnalyzerSettings::SetPreferedAnalyzerStartingSample | `?SetPreferedAnalyzerStartingSample@AnalyzerSettings@@QEAAX_J@Z` | 250 | 设置·PreferedAnalyzerStartingSample（按方法名推断） |
| AnalyzerSettings::SetReturnString | `?SetReturnString@AnalyzerSettings@@IEAAPEBDPEBD@Z` | 251 | 设置·ReturnString（按方法名推断） |
| AnalyzerSettings::SetUseSystemDisplayBase | `?SetUseSystemDisplayBase@AnalyzerSettings@@QEAAX_N@Z` | 259 | 设置·UseSystemDisplayBase（按方法名推断） |

### Analyzer（20 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
|---|---|---|---|
| Analyzer::CheckIfThreadShouldExit | `?CheckIfThreadShouldExit@Analyzer@@QEAAXXZ` | 133 | 检查·IfThreadShouldExit（按方法名推断） |
| Analyzer::DoesAnalyzerUseDevice | `?DoesAnalyzerUseDevice@Analyzer@@QEAA_N_K@Z` | 146 | 执行·esAnalyzerUseDevice（按方法名推断） |
| Analyzer::GetAnalyzerChannelData | `?GetAnalyzerChannelData@Analyzer@@QEAAPEAVAnalyzerChannelData@@AEAVChannel@@@Z` | 149 | 读取·AnalyzerChannelData（按方法名推断） |
| Analyzer::GetAnalyzerProgress | `?GetAnalyzerProgress@Analyzer@@QEAANXZ` | 151 | 读取·AnalyzerProgress（按方法名推断） |
| Analyzer::GetAnalyzerResults | `?GetAnalyzerResults@Analyzer@@QEAA_NPEAPEAVAnalyzerResults@@@Z` | 152 | 读取·AnalyzerResults（按方法名推断） |
| Analyzer::GetAnalyzerSettings | `?GetAnalyzerSettings@Analyzer@@QEAAPEAVAnalyzerSettings@@XZ` | 153 | 读取·AnalyzerSettings（按方法名推断） |
| Analyzer::GetSampleRate | `?GetSampleRate@Analyzer@@QEAAIXZ` | 202 | 读取·SampleRate（按方法名推断） |
| Analyzer::GetSimulationSampleRate | `?GetSimulationSampleRate@Analyzer@@QEAAIXZ` | 209 | 读取·SimulationSampleRate（按方法名推断） |
| Analyzer::GetTriggerSample | `?GetTriggerSample@Analyzer@@QEAA_KXZ` | 217 | 读取·TriggerSample（按方法名推断） |
| Analyzer::Init | `?Init@Analyzer@@QEAAXPEAVDeviceCollection@@PEAVConditionManager@@PEAVProgressManager@@@Z` | 227 | 初始化·（按方法名推断） |
| Analyzer::InitialWorkerThread | `?InitialWorkerThread@Analyzer@@QEAAXXZ` | 229 | 初始化·WorkerThread（按方法名推断） |
| Analyzer::IsValid | `?IsValid@Analyzer@@QEAA_NPEAVChannel@@I@Z` | 233 | 判断·Valid（按方法名推断） |
| Analyzer::KillThread | `?KillThread@Analyzer@@QEAAXXZ` | 234 | 终止·Thread（按方法名推断） |
| Analyzer::ReportProgress | `?ReportProgress@Analyzer@@QEAAX_K@Z` | 235 | 上报·Progress（按方法名推断） |
| Analyzer::SetAnalyzerResults | `?SetAnalyzerResults@Analyzer@@QEAAXPEAVAnalyzerResults@@@Z` | 239 | 设置·AnalyzerResults（按方法名推断） |
| Analyzer::SetAnalyzerSettings | `?SetAnalyzerSettings@Analyzer@@QEAAXPEAVAnalyzerSettings@@@Z` | 240 | 设置·AnalyzerSettings（按方法名推断） |
| Analyzer::SetThreadMustExit | `?SetThreadMustExit@Analyzer@@QEAAXXZ` | 257 | 设置·ThreadMustExit（按方法名推断） |
| Analyzer::StartProcessing | `?StartProcessing@Analyzer@@QEAAXXZ` | 264 | 启动·Processing（按方法名推断） |
| Analyzer::StartProcessing | `?StartProcessing@Analyzer@@QEAAX_K@Z` | 265 | 启动·Processing（按方法名推断） |
| Analyzer::StopWorkerThread | `?StopWorkerThread@Analyzer@@QEAAXXZ` | 266 | 停止·WorkerThread（按方法名推断） |

### SimpleArchive（18 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
|---|---|---|---|
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEAH@Z` | 78 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEAI@Z` | 79 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEAN@Z` | 80 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEAVChannel@@@Z` | 81 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEA_J@Z` | 82 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEA_K@Z` | 83 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NAEA_N@Z` | 84 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输入运算符> | `??5SimpleArchive@@QEAA_NPEAPEBD@Z` | 85 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_NAEAVChannel@@@Z` | 86 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_NH@Z` | 87 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_NI@Z` | 88 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_NN@Z` | 89 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_NPEBD@Z` | 90 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_N_J@Z` | 91 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_N_K@Z` | 92 | 特殊运算符（按名称推断） |
| SimpleArchive::<流输出运算符> | `??6SimpleArchive@@QEAA_N_N@Z` | 93 | 特殊运算符（按名称推断） |
| SimpleArchive::GetString | `?GetString@SimpleArchive@@QEAAPEBDXZ` | 210 | 读取·String（按方法名推断） |
| SimpleArchive::SetString | `?SetString@SimpleArchive@@QEAAXPEBD@Z` | 254 | 设置·String（按方法名推断） |

### AnalyzerHelpers（14 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
|---|---|---|---|
| AnalyzerHelpers::AdjustSimulationTargetSample | `?AdjustSimulationTargetSample@AnalyzerHelpers@@SA_K_KII@Z` | 121 | 调整·SimulationTargetSample（按方法名推断） |
| AnalyzerHelpers::AppendToFile | `?AppendToFile@AnalyzerHelpers@@SAXPEBEIPEAX@Z` | 129 | 追加·ToFile（按方法名推断） |
| AnalyzerHelpers::Assert | `?Assert@AnalyzerHelpers@@SAXPEBD@Z` | 130 | 按方法名推断的辅助操作 |
| AnalyzerHelpers::ConvertToSignedNumber | `?ConvertToSignedNumber@AnalyzerHelpers@@SA_J_KI@Z` | 140 | 转换有符号·Number（按方法名推断） |
| AnalyzerHelpers::Diff32 | `?Diff32@AnalyzerHelpers@@SAIII@Z` | 141 | 计算·32（按方法名推断） |
| AnalyzerHelpers::DoChannelsOverlap | `?DoChannelsOverlap@AnalyzerHelpers@@SA_NPEBVChannel@@I@Z` | 143 | 执行·ChannelsOverlap（按方法名推断） |
| AnalyzerHelpers::EndFile | `?EndFile@AnalyzerHelpers@@SAXPEAX@Z` | 147 | 结束·File（按方法名推断） |
| AnalyzerHelpers::GetNumberString | `?GetNumberString@AnalyzerHelpers@@SAX_KW4DisplayBase@@IPEADI@Z` | 192 | 读取·NumberString（按方法名推断） |
| AnalyzerHelpers::GetOnesCount | `?GetOnesCount@AnalyzerHelpers@@SAI_K@Z` | 193 | 读取·OnesCount（按方法名推断） |
| AnalyzerHelpers::GetTimeString | `?GetTimeString@AnalyzerHelpers@@SAX_K0IPEADI@Z` | 213 | 读取·TimeString（按方法名推断） |
| AnalyzerHelpers::IsEven | `?IsEven@AnalyzerHelpers@@SA_N_K@Z` | 231 | 判断·Even（按方法名推断） |
| AnalyzerHelpers::IsOdd | `?IsOdd@AnalyzerHelpers@@SA_N_K@Z` | 232 | 判断·Odd（按方法名推断） |
| AnalyzerHelpers::SaveFile | `?SaveFile@AnalyzerHelpers@@SAXPEBDPEBEI_N@Z` | 237 | 保存·File（按方法名推断） |
| AnalyzerHelpers::StartFile | `?StartFile@AnalyzerHelpers@@SAPEAXPEBD_N@Z` | 263 | 启动·File（按方法名推断） |

### AnalyzerChannelData（12 项）

| 方法（还原名） | 原始修饰名 | 序号 | 推测职责 |
