"""
AiBrain 启动入口
职责：检查环境 → 单实例清理 → 以独立进程启动 process_manager

由 start.bat 调用：
    venv312/Scripts/python.exe backend/launcher/start.py [--no-ui]
"""
import os
import sys
import subprocess
import time
import argparse

_BASE = os.path.dirname(os.path.abspath(__file__))           # backend/launcher/
_BACKEND = os.path.normpath(os.path.join(_BASE, '..'))       # backend/
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..', '..'))  # 项目根
_PYTHON = sys.executable  # 当前 venv 的 python
_PROJECT_ROOT_LOWER = _PROJECT_ROOT.lower()


def check_deps():
    """检查依赖是否满足"""
    r = subprocess.run(
        [_PYTHON, os.path.join(_BASE, '_boot_helper.py'), 'deps'],
        cwd=_PROJECT_ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("Missing dependencies detected, installing...")
        req = os.path.join(_PROJECT_ROOT, 'requirements.txt')
        subprocess.run([_PYTHON, '-m', 'pip', 'install', '-r', req], cwd=_PROJECT_ROOT)
        r2 = subprocess.run(
            [_PYTHON, os.path.join(_BASE, '_boot_helper.py'), 'deps'],
            cwd=_PROJECT_ROOT, capture_output=True, text=True,
        )
        if r2.returncode != 0:
            print("ERROR: Failed to install dependencies.")
            sys.exit(1)
    print("Dependencies OK.")


def kill_old_manager():
    """单实例保证：杀掉同项目的旧 process_manager（只杀进程本身，不带 /T）"""
    _self = os.getpid()
    killed = 0
    try:
        result = subprocess.run(
            ['wmic', 'process', "where", "name='python.exe'",
             'get', 'ProcessId,CommandLine,ExecutablePath', '/format:csv'],
            capture_output=True, text=True, timeout=10, cwd=_PROJECT_ROOT,
        )
        for line in result.stdout.splitlines():
            parts = line.split(',')
            if len(parts) < 4:
                continue
            pid_str = parts[-1].strip()
            cmd_line = parts[1].strip().lower()
            exe_path = parts[2].strip().lower()
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid == _self:
                continue
            if 'process_manager.py' not in cmd_line:
                continue
            # 通过 ExecutablePath 或命令行判断是否同一项目
            is_same_project = (
                _PROJECT_ROOT_LOWER in exe_path or
                _PROJECT_ROOT_LOWER in cmd_line
            )
            if is_same_project:
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                               capture_output=True, timeout=10)
                print(f"  [start] Killed old process_manager (PID {pid})")
                killed += 1
    except Exception as e:
        print(f"  [start] manager scan failed: {e}")
    return killed


def kill_old_services():
    """清理旧 Flask/Qdrant 等服务"""
    kill_script = os.path.join(_BASE, 'kill_old.py')
    subprocess.run([_PYTHON, kill_script], cwd=_PROJECT_ROOT, timeout=30)


def launch_manager(no_ui=False):
    """以独立新窗口启动 process_manager，完全脱离当前进程树"""
    manager = os.path.join(_BASE, 'process_manager.py')
    env = {
        **os.environ,
        'PYTHONPATH': f'{_PROJECT_ROOT};{_BACKEND}',
    }
    args = [_PYTHON, manager]
    if no_ui:
        args.append('--no-ui')

    proc = subprocess.Popen(
        args,
        cwd=_PROJECT_ROOT,
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"  [start] process_manager launched (PID {proc.pid})")
    return proc.pid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-ui', action='store_true')
    args = parser.parse_args()

    print("=== AiBrain Launcher ===")

    # 1. 检查依赖
    print("\n[1/4] Checking dependencies...")
    check_deps()

    # 2. 杀旧 manager
    print("\n[2/4] Stopping old process_manager...")
    n = kill_old_manager()
    if n:
        time.sleep(1)  # 等旧 manager 退出

    # 3. 清理旧服务
    print("\n[3/4] Killing old services (Flask/Qdrant)...")
    kill_old_services()
    time.sleep(0.5)

    # 4. 启动新 manager（独立后台进程）
    print("\n[4/4] Launching process_manager...")
    pid = launch_manager(no_ui=args.no_ui)

    print(f"\n=== Done. process_manager running (PID {pid}) ===\n")


if __name__ == '__main__':
    main()
