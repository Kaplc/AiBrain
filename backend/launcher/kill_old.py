"""清理 AiBrain 项目相关的旧进程

策略：通过端口锁定进程 PID → taskkill /F /T 终止整棵进程树

检测逻辑（不依赖进程名扫描）：
  1. 从 .port_config 读取本项目占用的端口
  2. netstat -ano 找出每个端口的 LISTENING PID
  3. taskkill /F /T 杀掉该 PID（连带子树）
  4. 兜底：扫描 Python 进程，匹配项目路径 + 入口文件名（处理漏网之鱼）
"""
import os
import subprocess


def _load_ports():
    """从 .port_config 读取端口（兼容 process_manager.py 的格式）"""
    _project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    config_path = os.path.join(_project_root, '.port_config')
    try:
        with open(config_path, 'r') as f:
            parts = f.read().strip().split(',')
        ports = [int(p.strip()) for p in parts if p.strip().isdigit()]
        return {
            'Flask': ports[0] if len(ports) > 0 else 18980,
            'Qdrant-HTTP': ports[1] if len(ports) > 1 else 18981,
            'Qdrant-gRPC': ports[2] if len(ports) > 2 else 18982,
        }
    except Exception:
        return {'Flask': 18980, 'Qdrant-HTTP': 18981, 'Qdrant-gRPC': 18982}


def _get_listening_pids():
    """返回 {port: pid} 所有当前处于 LISTENING 状态的端口"""
    result = subprocess.run(
        ['netstat', '-ano'],
        capture_output=True, text=True, timeout=10,
    )
    port_pid = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if 'LISTENING' not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        # 格式: TCP    0.0.0.0:port    0.0.0.0:0    LISTENING    pid
        try:
            local_addr = parts[1]
            if ':' in local_addr:
                port = int(local_addr.rsplit(':', 1)[-1])
            else:
                continue
            pid = int(parts[-1])
            port_pid[port] = pid
        except (ValueError, IndexError):
            continue
    return port_pid


def _kill_by_pid(pid: int) -> bool:
    """杀指定 PID 及整棵子树，返回是否成功"""
    try:
        r = subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 or '已终止' in r.stdout or 'has been terminated' in r.stdout.lower():
            return True
        return False
    except Exception:
        return False


def _guess_label(pid: int) -> str:
    """根据 PID 猜测进程类型（仅用于日志）"""
    try:
        r = subprocess.run(
            ['wmic', 'process', f'where ProcessId={pid}', 'get', 'CommandLine', '/format:list'],
            capture_output=True, text=True, timeout=3,
        )
        line = r.stdout.strip()
        if '--webview-only' in line:
            return 'WebView'
        elif '--flask-only' in line or 'start_flask' in line:
            return 'Flask'
        elif 'process_manager' in line:
            return 'Manager'
        elif 'brain_mcp' in line:
            return 'BrainMCP'
        elif 'wiki_mcp' in line:
            return 'WikiMCP'
        elif 'qdrant' in line.lower():
            return 'Qdrant'
        else:
            return 'Python'
    except Exception:
        return 'process'


def main():
    _project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    _self_pid = os.getpid()
    _parent_pid = os.getppid()
    _exclude_pids = {_self_pid, _parent_pid}

    ports = _load_ports()
    listening = _get_listening_pids()

    target_pids = set()
    port_report = []

    for name, port in ports.items():
        pid = listening.get(port)
        if pid and pid not in _exclude_pids:
            target_pids.add(pid)
            port_report.append(f"{name}:{port}→PID={pid}")

    if port_report:
        print(f"  [kill_old] ports in use: {', '.join(port_report)}")

    # 兜底：扫描 Python 进程（处理 kill_by_port 漏掉的残留进程）
    try:
        result = subprocess.run(
            ['wmic', 'process', "where", "name='python.exe'",
             'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=10,
        )
        proj_lower = _project_root.lower()
        keywords = ['app.py', 'process_manager.py', 'start_flask.py']
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith('Node'):
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            cmd_line = ','.join(parts[1:-1]).strip()
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid in _exclude_pids or pid in target_pids:
                continue
            if proj_lower in cmd_line.lower() and any(kw in cmd_line.lower() for kw in keywords):
                target_pids.add(pid)
                print(f"  [kill_old] fallback: found Python process PID={pid} ({cmd_line[:60]})")
    except Exception as e:
        print(f"  [warn] fallback python scan skipped: {e}")

    if not target_pids:
        print("  [kill_old] no old processes found")
        return

    print("=== Killing old processes ===")
    killed = 0
    failed = 0

    for pid in sorted(target_pids):
        label = _guess_label(pid)
        if _kill_by_pid(pid):
            print(f"  Killed {label} (PID {pid} + subtree)")
            killed += 1
        else:
            print(f"  Failed PID {pid}")
            failed += 1

    print(f"=== Done (killed={killed}, failed={failed}) ===")


if __name__ == '__main__':
    main()
