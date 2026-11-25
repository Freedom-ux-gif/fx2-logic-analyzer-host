# LogicWeb.exe 打包说明

把网页版上位机打包成**单文件 exe**，双击即可运行：自动起本地服务 → 打开浏览器 → 显示完整界面，全程不碰命令行。

## 一、怎么打包

在 `13_web` 目录下执行一条命令：

```bat
python -I make_app_exe.py
```

脚本会先检查前置条件（`static/index.html` 存在、PyInstaller 可导入），再调用 PyInstaller，打包完成后自动跑一次 `--check` 冒烟测试。

## 二、产物在哪

```
13_web\dist_app\LogicWeb.exe
```

约 30-40 MB。目录 `13_web\build\`、`13_web\dist_app\` 由打包脚本自动生成，可随时删除后重新打包。

## 三、怎么用

双击 `dist_app\LogicWeb.exe`，浏览器会自动打开 `http://127.0.0.1:8421`（若被占用则从 8422 起顺延）并显示上位机界面。关闭窗口内的服务或结束进程即可停止。

## 四、已知限制

- exe 约 30-40 MB（含 numpy 等依赖）。
- 首次启动较慢：单文件 exe 要解压到临时目录，约 3-8 秒。
- 杀毒软件可能误报（PyInstaller 打包程序的常见现象，添加信任即可）。
- 采集数据仍保存在 `Documents\LogicCapture\`，不受打包影响。
- 需要设备已插好并初始化（含 0x82 端点）才能采集；仅浏览界面不需要设备。
