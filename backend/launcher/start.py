"""
AiBrain 启动入口
职责：检查环境 → 统一清理旧进程 → 等待端口释放 → 启动 process_manager

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


def kill_all_old():
    """统一清理所有 AiBrain 旧进程（manager + flask + qdrant + mcp 等）

    通过项目路径 + 入口文件名匹配，不依赖端口。
    kill_old.py 会扫描所有含项目路径 + entry keyword 的进程并杀整棵树。
    """
    print("Cleaning old processes...")
    kill_script = os.path.join(_BASE, 'kill_old.py')
    r = subprocess.run([_PYTHON, kill_script], cwd=_PROJECT_ROOT, timeout=30)
    if r.returncode != 0:
        print("  [start] kill_old.py returned non-zero, continuing anyway")


def _load_ports_from_config():
    """从 .port_config 读取端口（兼容 process_manager.py 的格式）"""
    config_path = os.path.join(_PROJECT_ROOT, '.port_config')
    try:
        with open(config_path, 'r') as f:
            parts = f.read().strip().split(',')
        ports = [int(p.strip()) for p in parts if p.strip().isdigit()]
        return {
            'Flask': ports[0] if len(ports) > 0 else 18980,
            'Qdrant-HTTP': ports[1] if len(ports) > 1 else 18981,
        }
    except Exception:
        return {'Flask': 18980, 'Qdrant-HTTP': 18981}


def _is_port_in_use(port):
    """检查端口是否仍被 LISTENING"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                return True
    except Exception:
        pass
    return False


def wait_ports_free(timeout=15):
    """轮询直到关键端口全部释放（确保旧进程完全退出后再启动新 mgr）

    如果超时未释放，说明有残留进程持有端口（taskkill /T 可能没杀干净），
    此时追加一次通过端口反查 PID 的强制清理。
    """
    ports = _load_ports_from_config()
    deadline = time.time() + timeout
    first_check = True
    while time.time() < deadline:
        busy = []
        for name, port in ports.items():
            if _is_port_in_use(port):
                busy.append(f"{name}:{port}")
        if not busy:
            if not first_check:
                print(f"  Ports released: {list(ports.values())}")
            return True
        if first_check:
            print(f"  Waiting for ports: {busy}")
            first_check = False
        time.sleep(0.5)
    print(f"  WARNING: ports still occupied after {timeout}s: {busy}")
    print(f"  Attempting force cleanup by port...")
    _force_kill_by_port(ports)
    return False


def _force_kill_by_port(ports):
    """通过 netstat 端口反向查找 PID 并强杀（kill_old.py 的补充兜底）"""
    killed_any = False
    for name, port in ports.items():
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    pid_str = parts[-1]
                    try:
                        pid = int(pid_str)
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(pid)],
                            capture_output=True, timeout=5,
                        )
                        print(f"  Force killed residual PID {pid} on {name}:{port}")
                        killed_any = True
                    except (ValueError, subprocess.TimeoutExpired):
                        pass
        except Exception:
            pass
    if not killed_any:
        print(f"  No residual processes found for ports {list(ports.values())}")


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
    print("\n[1/3] Checking dependencies...")
    check_deps()

    # 2. 统一清理所有旧进程 + 等待端口释放
    print("\n[2/3] Cleaning old processes...")
    kill_all_old()
    print("Waiting for ports to be released...")
    wait_ports_free(timeout=15)

    # 3. 启动新 manager（独立后台进程）
    print("\n[3/3] Launching process_manager...")
    pid = launch_manager(no_ui=args.no_ui)

    print(f"\n=== Done. process_manager running (PID {pid}) ===\n")


if __name__ == '__main__':
    main()
