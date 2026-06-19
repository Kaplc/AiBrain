@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AiBrain - Stopping all services
echo === AiBrain Shutdown ===
echo.

REM 第1步：按端口清理
echo [1/3] Cleaning by port...
venv312\Scripts\python.exe backend\launcher\kill_old.py
if errorlevel 1 echo   (some processes may have exited already)

REM 第2步：深度清理残留
echo.
echo [2/3] Deep cleaning residual processes...
venv312\Scripts\python.exe -c "import subprocess,os,time;P=os.path.abspath('.');L=P.lower();[subprocess.run(['taskkill','/F','/T','/PID',p],capture_output=True,timeout=5) or print(f'  Killed {n} PID {p}') for n,f in[('Python','python.exe'),('Qdrant','qdrant.exe')]for l in(__import__('subprocess').run(['wmic','process','where',f\"name='{f}'\",'get','ProcessId,CommandLine','/format:csv'],capture_output=True,text=True,timeout=10).stdout.splitlines())if not l.startswith('Node')and','in l and L in l.lower()for p in[l.split(',')[-1].strip()]if p.isdigit()]"

REM 第3步：验证端口
echo.
echo [3/3] Checking ports...
venv312\Scripts\python.exe -c "import subprocess,os;P=os.path.abspath('.');d=set();exec(open(os.path.join(P,'.port_config')).read().translate(str.maketrans('','',',\n')));d.update(int(x)for x in __import__('re').findall(r'\d+',open(os.path.join(P,'.port_config')).read()));r=subprocess.run(['netstat','-ano'],capture_output=True,text=True,timeout=5);b=[l.strip()for l in r.stdout.splitlines()if'LISTENING'in l and any(f':{p}'in l.split()[1]for p in d)];exit(1)if b else[print('All ports free.')]"

if errorlevel 1 (
    echo.
    echo WARNING: Some ports still occupied - check Task Manager.
) else (
    echo.
    echo AiBrain has been fully stopped.
)
echo.
pause
