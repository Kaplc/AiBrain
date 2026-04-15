@echo off
echo === Starting Qdrant ===
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo Qdrant already running.
) else (
    start "" /MIN "C:\Users\v_zhyyzheng\Desktop\qdrant\qdrant.exe"
    echo Qdrant started.
    timeout /t 2 >NUL
)

echo === Starting Memory Manager UI ===
"C:\Users\v_zhyyzheng\Desktop\MemoryExtra\venv312\Scripts\python.exe" ^
    "C:\Users\v_zhyyzheng\Desktop\MemoryExtra\app.py"
