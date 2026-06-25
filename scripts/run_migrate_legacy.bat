@echo off
chcp 65001 >nul
title legacy migration

cd /d "%~dp0"
set BASE=%~dp0..

set VENV_PY=%BASE%\venv312\Scripts\python.exe
set SCRIPT=%BASE%\scripts\migrate_legacy_via_api.py

if not exist "%VENV_PY%" (
    echo ERROR: python not found at %VENV_PY%
    pause
    exit /b 1
)

echo ========================================
echo AiBrain legacy memory migration
echo ========================================
echo start: %DATE% %TIME%
echo.

"%VENV_PY%" "%SCRIPT%" 2>&1

echo.
echo exit code: %ERRORLEVEL%
echo end: %DATE% %TIME%
echo.
pause
