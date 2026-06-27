@echo off
cd /d "%~dp0"

echo 正在清理旧实例...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9999 ^| findstr LISTENING') do (
    echo 发现进程 PID=%%a，正在清理...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul
echo 清理完成

echo 正在启动拦截脚本...
powershell -ExecutionPolicy Bypass -Command "cd '%~dp0'; $python='..\venv312\Scripts\python.exe'; if (-not (Test-Path $python)) { $python='python' }; & $python sniff_claude.py"
pause
