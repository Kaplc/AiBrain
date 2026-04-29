@echo off
cd /d "%~dp0"
echo === AiBrain ===
venv312\Scripts\python.exe backend\launcher\start.py %*
