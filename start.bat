@echo off
setlocal enabledelayedexpansion

echo === AiBrain ===

:: ── 检查/创建虚拟环境 (Python 3.12+) ────────────────
echo === Checking Virtual Environment ===
if not exist "venv312\Scripts\python.exe" (
    echo Virtual environment not found.
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
"venv312\Scripts\python.exe" "backend\launcher\_boot_helper.py" deps 2>NUL
if %ERRORLEVEL% neq 0 (
    echo Missing dependencies detected, installing...
    echo This may take a few minutes on first run...
    call "venv312\Scripts\pip.exe" install -r "requirements.txt" 2>NUL
    "venv312\Scripts\python.exe" "backend\launcher\_boot_helper.py" deps 2>NUL
    if %ERRORLEVEL% neq 0 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
    echo All dependencies installed successfully.
) else (
    echo Dependencies OK.
)

:: ── 获取端口 ───────────────────────────────────────────
"venv312\Scripts\python.exe" "backend\launcher\_boot_helper.py" ports > "%TEMP%\mem_ports.txt" 2>&1

:: ── 启动 ProcessManager（统一管理 Qdrant + Flask + PyWebView）──
echo === Starting Process Manager ===
set "PYTHONPATH=%~dp0;%~dp0backend"
"venv312\Scripts\python.exe" "backend\launcher\process_manager.py" %*
