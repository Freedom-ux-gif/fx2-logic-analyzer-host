# REA 工具链就绪评估

> 范围：只读评估 `REA 工具源码仓库（非本仓库）`（REA MCP 工具源码仓库，v6.5.0，bin 为 `scripts/rea.mjs`）。未注册 MCP、未跑 setup、未改任何配置或仓库文件。

## 1. 实跑命令与实际输出

| 命令 | 实际输出 |
|---|---|
| `node -v` | `v24.16.0`（与大脑预期一致） |
| `node dist/cli.js --help`（在仓库根目录执行） | **无输出**（stdout/stderr 均为空，退出码 0）。确认大脑实测：该构建不含可打印的 help 子命令输出。 |
| `node dist/cli.js doctor --json` | **无输出**（stdout/stderr 均为空，退出码 0）。说明：`doctor` 在命令表中存在，但此调用方式未产出 JSON。 |
| `node -e "import('./dist/cliCommandNames.js').then(...)"` | `CLI_COMMANDS count: 153`；`CLI_COMMAND_NAMES count: 153`；`CLI_COMMAND_ALIASES count: 1 ["compare-bundles"]`；`CLI_COMMAND_TOOL_ALIASES count: 19`；`MCP_TOOLS_WITHOUT_DEDICATED_CLI count: 65`。 |

- 判断：`dist/cli.js` 不是面向终端打印帮助/诊断的入口，或此构建的相关命令被裁剪；真正权威的命令清单在 `dist/cliCommandNames.js`（对应 `src/cliCommandNames.ts`）。[本机实读]
- 本报告不改仓库、不注册 MCP、不跑 setup；命令名全部从 `dist/cliCommandNames.js` 静态读取。

## 2. 可用命令名表（来自 `dist/cliCommandNames.js`，153 个 CLI 命令）

> 说明：下表逐项照抄 `CLI_COMMANDS` 的值（命令名），共 153 项；别名 `compare-bundles` 单列于表后。另有 65 个 MCP 专属工具（无独立 CLI 命令），见 2.2。

### 2.1 CLI 命令（153 个）

| # | 命令 | # | 命令 | # | 命令 |
|---|---|---|---|---|---|
| 1 | inspect-packet-fields | 2 | inspect-packet-capture | 3 | inspect-signal-decoders |
| 4 | decode-signal-recording | 5 | compare-wasm-interfaces | 6 | inspect-wasm-artifact |
| 7 | inspect-sqlite-database | 8 | inspect-evm-interface | 9 | inspect-web-network-capture |
| 10 | observe-web-execution | 11 | inspect-web-event-listeners | 12 | trace-web-source-location |
| 13 | trace-web-module-imports | 14 | analyze | 15 | inspect |
| 16 | decompile | 17 | setup | 18 | doctor |
| 19 | uninstall | 20 | update | 21 | xrefs |
| 22 | trace | 23 | trace-native-ui-action | 24 | inspect-native-dispatch-metadata |
| 25 | capabilities | 26 | providers | 27 | function |
| 28 | annotate-native-function | 29 | inspect-native-api | 30 | instructions |
| 31 | search | 32 | import-reference-source | 33 | inspect-artifact |
| 34 | extract-artifact | 35 | decode-interface-builder | 36 | inspect-keyed-archive |
| 37 | trace-dylib-resolution | 38 | inspect-native-data-type | 39 | inspect-native-load-image |
| 40 | read-bytes | 41 | search-bytes | 42 | address-to-file-offset |
| 43 | trace-native-values | 44 | inspect-native-instruction | 45 | resolve-native-call-targets |
| 46 | inspect-asset-catalog | 47 | inspect-managed-artifact | 48 | inspect-recorded-crash |
| 49 | inspect-binary-layout | 50 | list-cutter-sessions | 51 | cutter-command |
| 52 | inspect-with-objdump | 53 | list-objdump-architectures | 54 | execute-rizin-command |
| 55 | debug-with-gdb | 56 | debug-with-rizin | 57 | inspect-go-binary |
| 58 | inspect-rust-binary | 59 | inspect-pe-resources | 60 | inspect-analysis-view |
| 61 | list-frida-devices | 62 | list-frida-processes | 63 | instrument-with-frida |
| 64 | inspect-evidence-bundle | 65 | inspect-firmware-regions | 66 | extract-firmware |
| 67 | inspect-android-package | 68 | inspect-pcap-client | 69 | inspect-pcap-capture |
| 70 | identify-flutter-build | 71 | inspect-dart-aot | 72 | inspect-apktool-client |
| 73 | decode-android-resources | 74 | inspect-adb-client | 75 | list-adb-devices |
| 76 | inspect-adb-device | 77 | list-adb-packages | 78 | pull-adb-package |
| 79 | read-adb-logcat | 80 | inspect-adb-package | 81 | pull-adb-file |
| 82 | push-adb-file | 83 | capture-adb-screen | 84 | list-adb-processes |
| 85 | list-adb-directory | 86 | list-adb-features | 87 | list-adb-services |
| 88 | inspect-adb-display | 89 | inspect-adb-window | 90 | read-adb-setting |
| 91 | collect-adb-bugreport | 92 | resolve-adb-packages | 93 | install-adb-package |
| 94 | uninstall-adb-package | 95 | start-adb-app | 96 | start-adb-activity |
| 97 | stop-adb-app | 98 | search-android-classes | 99 | inspect-android-class |
| 100 | inspect-android-method | 101 | trace-android-references | 102 | inspect-jeb-client |
| 103 | open-jeb-project | 104 | list-jeb-units | 105 | decompile-jeb-item |
| 106 | inspect-managed-members | 107 | inspect-managed-native-boundaries | 108 | compare-managed-members |
| 109 | verify-managed-native-boundaries | 110 | import-managed-reconstruction | 111 | project-managed-application-graph |
| 112 | observe-native-ui | 113 | observe-native-calls | 114 | capture-native-ui-scenario |
| 115 | inspect-macho | 116 | inspect-signature | 117 | list-architectures |
| 118 | inspect-plist | 119 | demangle-swift | 120 | evidence-import |
| 121 | evidence-export | 122 | compare | 123 | capture-process |
| 124 | compare-process-captures | 125 | list-browser-targets | 126 | inspect-web-page |
| 127 | analyze-web-bundle | 128 | export-web-scripts | 129 | recover-javascript-sources |
| 130 | observe-web-session | 131 | discover-webmcp-tools | 132 | compare-web-captures |
| 133 | capture-web-screenshot | 134 | compare-web-screenshots | 135 | capture-browser-scenario |
| 136 | list-electron-targets | 137 | inspect-electron-page | 138 | inspect-electron-fuses |
| 139 | capture-electron-scenario | 140 | list-javascript-runtime-targets | 141 | observe-javascript-runtime |
| 142 | analyze-javascript-application | 143 | reconcile-javascript-runtime | 144 | trace-application-feature |
| 145 | trace-javascript-semantics | 146 | compare-application-versions | 147 | compare-source-to-bundle |
| 148 | compare-javascript-export-shapes | 149 | build-reconstruction-obligation-ledger | 150 | evaluate-reconstruction-coverage |
| 151 | project-android-application-graph | 152 | project-apple-application-graph | 153 | project-harmony-application-graph |

- 别名（1 个）：`compare-bundles`（映射到 MCP `compare_bundles`）。[本机实读]

### 2.2 无独立 CLI 命令的 MCP 工具（65 个，`MCP_TOOLS_WITHOUT_DEDICATED_CLI`）

`address_name`, `comment`, `current_address`, `current_procedure`, `current_document`, `goto_address`, `inline_comment`, `list_bookmarks`, `list_documents`, `list_names`, `list_procedures`, `list_segments`, `list_strings`, `next_address`, `prev_address`, `procedure_address`, `procedure_assembly`, `procedure_callees`, `procedure_callers`, `procedure_info`, `procedure_references`, `resolve_containing_procedure`, `set_address_name`, `set_addresses_names`, `set_bookmark`, `set_comment`, `set_inline_comment`, `unset_bookmark`, `get_objc_classes`, `get_objc_protocols`, `batch_decompile`, `get_call_graph`, `analyze_swift_types`, `find_xrefs_to_name`, `trace_call_path`, `open_binary`, `close_binary`, `binary_session`, `export_evidence_bundle`, `import_evidence_bundle`, `compare_artifacts`, `compare_functions`, `find_changed_behavior`, `build_call_path`, `correlate_static_and_runtime`, `verify_reconstruction`, `list_unknowns`, `record_unknown`, `update_unknown`, `verify_unknown_resolution`, `get_evidence_bundle`, `get_navigation_context`, `inspect_address_context`, `start_gdb_session`, `gdb_session_status`, `close_gdb_session`, `start_rizin_debug_session`, `rizin_debug_session_status`, `close_rizin_debug_session`, `start_frida_session`, `load_frida_script`, `resume_frida_session`, `unload_frida_script`, `frida_session_status`, `close_frida_session`。[本机实读]

- 注：大脑所述「207 个工具」≈ 153 CLI 命令 + 1 别名 + 65 MCP-only 工具中的可调用面；本报告以源码实际枚举为准（153 + 1 + 65，存在少量别名重叠）。[推断，未验证]

## 3. 评估结论：哪些 REA 工具能直接用于本项目的 Windows 原生 PE 逆向？

### 3.1 相关（可用于 PE / 原生二进制静态分析）

| 工具/命令 | 用途 | 对本项目 |
|---|---|---|
| `open_binary` / `close_binary` / `binary_session`（MCP） | 打开并持有 PE 会话 | 对未混淆 DLL 有效；对 `Logic.exe` 无效（见第 4 节） |
| `binary_overview`（由 `analyze` / `inspect` 映射） | 二进制总览 | 可用于 DLL 基线 |
| `inspect-binary-layout` / `list_segments` / `list_names` | 节区/符号 | 可用于 DLL |
| `inspect-pe-resources` | PE 资源段 | 可用于 DLL/EXE（资源不受代码混淆影响） |
| `inspect-signature` | 签名信息 | 可用于原厂 DLL 是否签名 |
| `read-bytes` / `search-bytes` / `address-to-file-offset` | 字节读取与搜索 | 可用于定位协议字符串/常量 |
| `list_strings` / `search`（映射 `search_strings`/`search_procedures`） | 字符串提取 | 关键：可从 DLL 提取协议相关字符串 |
| `instructions` / `procedure_assembly` / `disassemble` 类 (`inspect-native-instruction`, `resolve-native-call-targets`) | 反汇编 | 对未混淆 DLL 有效 |
| `decompile` / `procedure_pseudo_code` / `function` | 伪代码/函数分析 | 对未混淆 DLL 有效 |
| `xrefs` / `procedure_xrefs` / `get_call_graph` / `trace_call_path` | 交叉引用与调用图 | 可用于 DLL 控制流 |
| `compare` / `compare_artifacts` / `compare_functions` / `find_changed_behavior` / `compare-process-captures` | 差异对比 | 可用于版本/插件间对比 |
| `inspect-native-api` / `annotate-native-function` / `trace-native-values` / `observe-native-calls` | 原生 API/调用观察 | 可辅助理解 DLL 行为 |
| `inspect-native-load-image` / `inspect-native-data-type` | 加载镜像/数据类型 | 可用于 PE 结构分析 |
| `inspect-with-objdump` / `execute-rizin-command` / `debug-with-gdb` / `debug-with-rizin`（CLI）/ `start_gdb_session` / `start_rizin_debug_session`（MCP） | 外部反汇编/调试后端 | 依赖本机是否安装 objdump/rizin/gdb；本机 `which` 均未找到（见 `toolchain.md`） |
| `instrument-with-frida` / `list-frida-devices` / `list-frida-processes` / Frida 会话类 | 运行时插桩 | 本机 Python 侧有 frida 17.23.3，但 REA 的 Frida 集成是否可用未在本次只读评估中验证 [推断，未验证] |
| `inspect-pcap-capture` / `inspect-pcap-client` / `inspect-packet-capture` / `inspect-packet-fields` | 抓包检查 | 可用于后续 USB/网络抓包对账（是否支持 USBPcap pcap 待验证） [推断，未验证] |
| `inspect-evidence-bundle` / `evidence-import` / `evidence-export` | 证据包 | 可用于归档分析证据 |

### 3.2 不适用（与本项目无关）

- **Android 类**：`inspect-android-package`、`inspect-apktool-client`、`decode-android-resources`、全部 `adb-*` 命令（list/pull/push/install/start/stop 等）、`search-android-classes`、`inspect-android-class/method`、`trace-android-references`、`project-android-application-graph`、`inspect-jeb-client` / `open-jeb-project` / `decompile-jeb-item` 等。[本机实读]
- **Electron / 浏览器 / JS 类**：`list-browser-targets`、`inspect-web-page`、`analyze-web-bundle`、`export-web-scripts`、`recover-javascript-sources`、`observe-web-session`、`compare-web-captures`、`capture-web-screenshot(s)`、`capture-browser-scenario`、`list-electron-targets`、`inspect-electron-page`、`inspect-electron-fuses`、`capture-electron-scenario`、`list-javascript-runtime-targets`、`observe-javascript-runtime`、`analyze-javascript-application`、`trace-javascript-semantics`、`compare-source-to-bundle` 等。[本机实读]
- **Apple / Swift / Mach-O 类**：`inspect-macho`、`inspect-plist`、`demangle-swift`、`inspect-keyed-archive`、`trace-dylib-resolution`、`decode-interface-builder`、`inspect-asset-catalog`、`get_objc_classes`、`get_objc_protocols`、`analyze_swift_types`、`project-apple-application-graph` 等。[本机实读]
- **其他无关**：WASM、EVM、Flutter/Dart、SQLite、HarmonyOS application graph、固件分区（`inspect-firmware-regions`/`extract-firmware`，本项目目标是 Windows PE 不是固件）。[本机实读]
- **敏感管理类**：`setup` / `uninstall` / `update` / `install-adb-package` 等会改环境，本次不执行。[本机实读]

## 4. 关键事实：混淆决定 REA 的用武之地

- **本项目目标 `Logic.exe` 已混淆（`.text` 熵 8.00），REA 的反汇编/伪代码能力对它无效**；静态反汇编得到的是无意义字节，不能靠 REA（或任何静态反汇编器）直接还原逻辑。[本机实读] [推断，未验证——基于大脑实测的熵值与「静态反汇编无效」结论]
- **REA 真正有用的对象是 `Analyzer.dll` 和 25 个插件 DLL（未混淆）**：这些是原生 PE，未混淆，可用 `open_binary` + `search`/`list_strings` + `inspect-native-instruction` + `decompile` + `xrefs` + `compare` 做静态分析，提取协议相关字符串、函数与控制流，作为抓包对账的辅助线索。[本机实读 + 推断，未验证]
- 对 `Logic.exe` 的有效路径仍是运行时抓包（WinUSB 控制传输 + bulk 端点），REA 不能替代；REA 只在「分析未混淆的 DLL 插件」这一侧提供价值。[本机实读]
- 本次为只读评估：**未注册 MCP、未跑 setup、未改 `逆向工程rea` 仓库任何文件、未改任何配置**。[本机实读]
