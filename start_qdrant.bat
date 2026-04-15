@echo off
setlocal enabledelayedexpansion

echo === Checking Dependencies ===
"venv312\Scripts\python.exe" -c "import flask, webview, qdrant_client" 2>NUL
if %ERRORLEVEL% neq 0 (
    echo Missing dependencies, installing...
    "venv312\Scripts\pip.exe" install -r "backend\requirements.txt"
    if %ERRORLEVEL% neq 0 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo === Stopping existing app ===
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":18765.*LISTENING"') do (
    taskkill /F /PID %%a >NUL 2>&1
)

echo === Starting Qdrant ===
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo Qdrant already running.
) else (
    start "" /MIN "backend\qdrant\qdrant.exe"
    echo Qdrant started.
    timeout /t 2 >NUL
)

echo === Starting Memory Manager ===
set "PYTHONPATH=%~dp0"
"venv312\Scripts\python.exe" "backend\app.py"
