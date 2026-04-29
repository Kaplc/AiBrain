"""快速杀掉占用项目端口的旧进程（替代慢速的 PowerShell kill_ports.ps1）

策略：先收集所有需要杀的目标 PID → 用 taskkill /F /T 终止整棵进程树
  /F = 强制终止
  /T = 终止该进程及所有由它启动的子进程（解决 reloader 父子残留）

匹配规则：
  - A1: 占用 .port_config 中端口的进程
  - A2: 命令行含 app.py 或 start_flask.py 且路径在项目目录下的 python 进程
      （覆盖 Flask/PyWebView + reloader 父进程，排除 kill_old.py 自身及其他脚本）
  - A3: 项目目录下的 qdrant.exe
"""
import os
import subprocess


def main():
    _project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    _project_root_lower = _project_root.lower()
    _self_pid = os.getpid()
    # 排除父进程（process_manager.py 调用 kill_old 时，父进程也不能杀）
    _parent_pid = os.getppid()
    _exclude_pids = {_self_pid, _parent_pid}

    # ── A. 收集目标 PID ──────────────────────────────
    target_pids = set()

    # A1: 占用目标端口的进程
    config_path = os.path.join(_project_root, '.port_config')
    try:
        with open(config_path, 'r') as f:
            raw = f.read().strip()
        ports = [int(p.strip()) for p in raw.split(',') if p.strip().isdigit()]
    except (FileNotFoundError, ValueError):
        ports = []

    if ports:
        result = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == 'TCP' and 'LISTENING' in line:
                addr = parts[1]
                pid_str = parts[-1]
                if ':' in addr:
                    port_str = addr.rsplit(':', 1)[-1]
                    try:
                        port = int(port_str)
                        if port in ports:
                            target_pids.add(int(pid_str))
                    except ValueError:
                        pass

    # A2: 本项目 app.py/start_flask.py 相关 python 进程（Flask + PyWebView + reloader 父）
    try:
        result = subprocess.run(
            ['wmic', 'process', "where", "name='python.exe'",
             'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            # csv 格式: Node,CommandLine,ProcessId
            parts = line.split(',')
            if len(parts) < 3:
                continue
            # 最后一列是 PID，中间列是 CommandLine（可能含逗号，取除第一列和最后列的所有内容）
            pid_str = parts[-1].strip()
            cmd_line = ','.join(parts[1:-1]).strip()
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid in _exclude_pids:
                continue
            cmd_lower = cmd_line.lower()
            is_app_process = 'app.py' in cmd_lower or 'start_flask' in cmd_lower
            is_our_path = _project_root_lower in cmd_lower
            if not (is_app_process and is_our_path):
                continue
            target_pids.add(pid)
    except Exception as e:
        print(f"  [warn] wmic scan skipped: {e}")

    # A3: 本项目目录下的残留 qdrant.exe
    try:
        result = subprocess.run(
            ['wmic', 'process', "where", "name='qdrant.exe'",
             'get', 'ProcessId,ExecutablePath', '/format:csv'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            # csv 格式: Node,ExecutablePath,ProcessId
            parts = line.split(',')
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            exe_path = ','.join(parts[1:-1]).strip()
            if _project_root_lower in exe_path.lower():
                try:
                    target_pids.add(int(pid_str))
                except (ValueError, IndexError):
                    pass
    except Exception as e:
        print(f"  [warn] qdrant scan skipped: {e}")

    if not target_pids:
        return

    # ── B. 执行终止（taskkill /F /T 整棵树）────────
    print("=== Killing old processes ===")
    killed = 0
    failed = 0

    for pid in sorted(target_pids):
        r = subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 or '已终止' in r.stdout or 'has been terminated' in r.stdout.lower():
            killed += 1
            label = _guess_label(pid)
            print(f"  Killed {label} (PID {pid} + subtree)")
        else:
            failed += 1
            err_msg = r.stderr.strip() or r.stdout.strip()
            print(f"  Failed PID {pid}: {err_msg[:80]}")

    print(f"=== Done (killed={killed}, failed={failed}) ===")


def _guess_label(pid: int) -> str:
    """根据 PID 猜测进程类型（仅用于日志显示）"""
    try:
        r = subprocess.run(
            ['wmic', 'process', f'where ProcessId={pid}', 'get', 'CommandLine', '/format:list'],
            capture_output=True, text=True, timeout=3
        )
        line = r.stdout.strip()
        if '--webview-only' in line:
            return 'PyWebView'
        elif '--flask-only' in line or 'start_flask' in line:
            return 'Flask'
        else:
            return 'python'
    except Exception:
        return 'process'


if __name__ == '__main__':
    main()
