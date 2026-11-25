@echo off
rem 双击本文件启动逻辑分析仪网页上位机。
rem 如果提示“python 不是内部或外部命令”，请把下面的 python 改成完整路径，
rem 例如："C:\Users\你的用户名\AppData\Local\Programs\Python\Python314\python.exe" -I launcher.py %*
chcp 65001 >nul
cd /d "%~dp0"
python -I launcher.py %*
pause
