@echo off
setlocal enabledelayedexpansion

echo === Memory Manager ===

:: ── 杀掉占用本项目端口的旧进程 ────────────────────────────
powershell -ExecutionPolicy Bypass -File "%~dp0kill_ports.ps1"

ping -n 2 127.0.0.1 >NUL 2>&1

:: ── 检查/创建虚拟环境 (Python 3.12+) ────────────────
echo === Checking Virtual Environment ===
if not exist "venv312\Scripts\python.exe" (
    echo Virtual environment not found.
    :: 查找任意 Python 3.12+（优先使用已安装的版本）
    set "PYTHON312="
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PYTHON312=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "C:\Python312\python.exe" (
        set "PYTHON312=C:\Python312\python.exe"
    ) else if exist "C:\Python313\python.exe" (
        set "PYTHON312=C:\Python313\python.exe"
    ) else for %%p in (python) do (
        %%p --version 2>NUL | findstr /C:"3.1" >NUL && set "PYTHON312=%%p"
    )
    if "!PYTHON312!"=="" (
        echo Python 3.12+ not found. Please install Python 3.12 or higher.
        echo   https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo Found Python: !PYTHON312!
    echo Creating virtual environment...
    "!PYTHON312!" -m venv venv312
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 显示虚拟环境版本
for /f "tokens=2" %%v in ('"venv312\Scripts\python.exe" --version 2^>NUL') do set PY_VER=%%v
echo Virtual Environment: Python %PY_VER%

:: ── 检查依赖 ──────────────────────────────────────────
echo === Checking Dependencies ===
"venv312\Scripts\python.exe" "backend\_boot_helper.py" deps 2>NUL
if %ERRORLEVEL% neq 0 (
    echo Missing dependencies detected, installing...
    echo This may take a few minutes on first run...
    call "venv312\Scripts\pip.exe" install -r "backend\requirements.txt" 2>NUL
    :: 验证所有包是否安装成功（忽略 pip 升级提示导致的非零退出码）
    "venv312\Scripts\python.exe" "backend\_boot_helper.py" deps 2>NUL
    if %ERRORLEVEL% neq 0 (
        echo Failed to install dependencies. Please check your network connection or Python installation.
        pause
        exit /b 1
    )
    echo All dependencies installed successfully.
) else (
    echo Dependencies OK.
)

:: ── 获取端口（首次自动分配，后续读配置文件）───────────
echo === Getting ports ===
"venv312\Scripts\python.exe" "backend\_boot_helper.py" ports > "%TEMP%\mem_ports.txt" 2>&1
set /p PORT_RESULT=<"%TEMP%\mem_ports.txt"

:: 去掉可能的额外输出行，只取第一行逗号分隔的数字
for /f "tokens=1,2,3,4,5 delims=," %%a in ("%PORT_RESULT%") do (
    set "FLASK_PORT=%%a"
    set "QDRANT_HTTP=%%b"
    set "QDRANT_GRPC=%%c"
    set "EXTRA_PORT1=%%d"
    set "EXTRA_PORT2=%%e"
)

echo   Flask Port : %FLASK_PORT%
echo   Qdrant HTTP: %QDRANT_HTTP%
echo   Qdrant gRPC: %QDRANT_GRPC%

:: ── 生成 Qdrant 配置 ───────────────────────────────────
(
echo service:
echo   host: 0.0.0.0
echo   http_port: %QDRANT_HTTP%
echo   grpc_port: %QDRANT_GRPC%
echo.
echo storage:
echo   storage_path: ./storage
) > "backend\qdrant\config\config.yaml"

:: ── 启动 Qdrant ─────────────────────────────────────────
echo === Starting Qdrant ===
netstat -ano 2>NUL | findstr ":%QDRANT_HTTP%.*LISTENING" >NUL
if %ERRORLEVEL% == 0 (
    echo Qdrant already running on port %QDRANT_HTTP%.
) else (
    start "" /MIN "backend\qdrant\qdrant.exe" --config-path "backend\qdrant\config\config.yaml"
    echo Qdrant started on port %QDRANT_HTTP%, waiting for it to be ready...
    :: 通过 HTTP API 等待 Qdrant 完全就绪（最多 60 秒）
    set "QDRANT_WAIT=0"
    :wait_qdrant
    ping -n 2 127.0.0.1 >NUL 2>&1
    "venv312\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%QDRANT_HTTP%/healthz', timeout=3)" 2>NUL
    if !ERRORLEVEL! equ 0 (
        echo Qdrant is ready.
    ) else (
        set /a QDRANT_WAIT+=1
        if !QDRANT_WAIT! lss 60 (
            goto wait_qdrant
        ) else (
            echo WARNING: Qdrant did not respond within 60 seconds, continuing anyway...
        )
    )
)

:: ── 启动应用 ──────────────────────────────────────────
echo === Starting Memory Manager ===
set "PYTHONPATH=%~dp0;%~dp0backend"
set "FLASK_PORT=%FLASK_PORT%"
set "QDRANT_HTTP_PORT=%QDRANT_HTTP%"
set "QDRANT_GRPC_PORT=%QDRANT_GRPC%"
"venv312\Scripts\python.exe" "backend\app.py"
