"""
AiBrain 统一进程管理器
管理 Qdrant + Flask + PyWebView 的完整生命周期

用法:
  python backend/launcher/process_manager.py          # 正常启动（全部组件）
  python backend/launcher/process_manager.py --no-ui  # 无 UI 模式（仅 Qdrant + Flask）

进程树:
  process_manager.py (主进程, PID=X)
  ├── qdrant.exe       (子进程)
  ├── python app.py --flask-only   (子进程, 1个)
  └── python app.py --webview-only (子进程, 1个)
  总共 4 个进程，固定不变
"""
import os
import sys
import signal
import socket
import subprocess
import time
import urllib.request
import argparse

# ── 路径 ──────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))          # backend/launcher/
_BACKEND = os.path.normpath(os.path.join(_BASE, '..'))      # backend/
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..', '..'))  # 项目根
_PYTHON = os.path.join(_PROJECT_ROOT, 'venv312', 'Scripts', 'python.exe')
_QDRANT_EXE = os.path.join(_PROJECT_ROOT, 'qdrant', 'qdrant.exe')
_QDRANT_CONFIG = os.path.join(_PROJECT_ROOT, 'qdrant', 'config', 'config.yaml')
_LOGS_DIR = os.path.join(_BACKEND, 'logs')                  # backend/logs/
os.makedirs(_LOGS_DIR, exist_ok=True)

# ── 端口 ──────────────────────────────────────────────
def _load_ports():
    """从 .port_config 读取端口"""
    config_path = os.path.join(_PROJECT_ROOT, '.port_config')
    with open(config_path, 'r') as f:
        parts = f.read().strip().split(',')
    ports = [int(p.strip()) for p in parts if p.strip().isdigit()]
    return {
        'flask': ports[0] if len(ports) > 0 else 18980,
        'qdrant_http': ports[1] if len(ports) > 1 else 18981,
        'qdrant_grpc': ports[2] if len(ports) > 2 else 18982,
    }


# ── 进程管理 ──────────────────────────────────────────
class ProcessManager:
    def __init__(self, no_ui=False):
        self.ports = _load_ports()
        self.no_ui = no_ui
        self.procs = {}       # name → Popen
        self._running = True

    # ── 启动组件 ──
    def start_qdrant(self):
        """启动 Qdrant（如果未运行）"""
        if self._is_port_listening(self.ports['qdrant_http']):
            print(f"  [qdrant] Already running on port {self.ports['qdrant_http']}")
            return True

        # 生成配置
        self._write_qdrant_config()

        print(f"  [qdrant] Starting on port {self.ports['qdrant_http']}...")
        proc = subprocess.Popen(
            [_QDRANT_EXE, '--config-path', _QDRANT_CONFIG],
            cwd=_PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.procs['qdrant'] = proc

        # 等待就绪
        url = f'http://127.0.0.1:{self.ports["qdrant_http"]}/healthz'
        if self._wait_url(url, timeout=60, label='qdrant'):
            print(f"  [qdrant] Ready (PID {proc.pid})")
            return True
        else:
            print(f"  [qdrant] WARNING: not ready after 60s, continuing...")
            return False

    def start_flask(self):
        """启动 Flask 服务"""
        # 构建前端 dist
        print(f"  [flask] Building frontend...")
        web_dir = os.path.join(_PROJECT_ROOT, 'web')
        build_result = subprocess.run(
            'npm run build',
            cwd=web_dir,
            capture_output=True, timeout=120,
            shell=True,
        )
        if build_result.returncode != 0:
            print(f"  [flask] Build failed: {build_result.stderr.decode('utf-8', errors='replace')[:200]}")
        else:
            print(f"  [flask] Build done")

        env = {
            **os.environ,
            'PYTHONPATH': f'{_PROJECT_ROOT};{_BACKEND}',
            'FLASK_PORT': str(self.ports['flask']),
            'QDRANT_HTTP_PORT': str(self.ports['qdrant_http']),
            'QDRANT_GRPC_PORT': str(self.ports['qdrant_grpc']),
            'FLASK_RELOAD': '0',  # 由 ProcessManager 管理重启，不用 reloader
        }
        print(f"  [flask] Starting on port {self.ports['flask']}...")
        proc = subprocess.Popen(
            [_PYTHON, os.path.join(_BACKEND, 'app.py'), '--flask-only'],
            cwd=_PROJECT_ROOT,
            env=env,
        )
        self.procs['flask'] = proc

        # 等待就绪
        url = f'http://127.0.0.1:{self.ports["flask"]}/health'
        if self._wait_url(url, timeout=30, label='flask'):
            print(f"  [flask] Ready (PID {proc.pid})")
            return True
        else:
            print(f"  [flask] WARNING: not ready after 30s")
            return False

    def restart_flask(self):
        """重启 Flask 服务（供文件监控调用）

        策略：优先通过端口查找并杀死实际监听的 Flask 进程，
        不依赖 self.procs 记录（可能与实际运行的进程不一致）
        """
        _dbg_path = os.path.join(_LOGS_DIR, 'restart_trace.log')
        try:
            with open(_dbg_path, 'a') as _f:
                _f.write(f"[{time.strftime('%H:%M:%S')}] === restart_flask() ENTER ===\n")
                _f.write(f"  procs keys={list(self.procs.keys())}\n")
                _f.write(f"  flask port={self.ports.get('flask')}\n")
                proc = self.procs.get('flask')
                _f.write(f"  procs['flask'] pid={proc.pid if proc else None} alive={proc.poll() is None if proc else 'N/A'}\n")
        except Exception:
            pass

        print(f"  [flask] Restarting...")
        flask_port = self.ports['flask']

        # 从 procs 移除引用，防止 monitor 双重重启
        proc = self.procs.pop('flask', None)

        # 1. 通过端口查找并杀死实际监听 Flask 的进程（主要手段）
        killed_pids = []
        try:
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{flask_port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    pid_str = parts[-1]
                    try:
                        r = subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', pid_str],
                            capture_output=True, timeout=5,
                        )
                        killed_pids.append(pid_str)
                        print(f"  [flask] Killed PID {pid_str} (rc={r.returncode})")
                    except Exception as e:
                        print(f"  [flask] Port-kill PID {pid_str} failed: {e}")
        except Exception as e:
            print(f"  [flask] netstat check failed: {e}")

        with open(_dbg_path, 'a') as _f:
            _f.write(f"  [STEP1] killed_pids={killed_pids}\n")

        # 2. 强制杀死 procs 记录的 Flask 进程（无论是否在 step1 中已杀）
        if proc and proc.poll() is None:
            try:
                r2 = subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                    capture_output=True, timeout=10,
                )
                print(f"  [flask] Also killed recorded proc PID {proc.pid} (rc={r2.returncode})")
                with open(_dbg_path, 'a') as _f:
                    _f.write(f"  [STEP2] fallback kill PID={proc.pid} rc={r2.returncode}\n")
            except Exception as e:
                print(f"  [flask] Recorded-proc kill failed: {e}")
                with open(_dbg_path, 'a') as _f:
                    _f.write(f"  [STEP2] fallback KILL FAILED: {e}\n")
        elif proc:
            with open(_dbg_path, 'a') as _f:
                _f.write(f"  [STEP2] proc=None or already dead (pid={proc.pid if proc else None})\n")

        # 3. 轮询等端口释放（用 socket 试绑定，最多 5 秒）
        port_freed = False
        for attempt in range(10):
            if self._is_port_free(flask_port):
                port_freed = True
                break
            time.sleep(0.5)

        with open(_dbg_path, 'a') as _f:
            _f.write(f"  [STEP3] port freed={port_freed} after {(attempt+1)*0.5:.1f}s\n")
            _f.write(f"  [STEP4] calling start_flask()...\n")
        ret = self.start_flask()
        with open(_dbg_path, 'a') as _f:
            _f.write(f"  [STEP4] start_flask() returned={ret}\n")
            _f.write(f"[{time.strftime('%H:%M:%S')}] === restart_flask EXIT ===\n\n")
        return ret

    def start_webview(self):
        """启动 PyWebView 窗口"""
        if self.no_ui:
            print("  [webview] Skipped (--no-ui)")
            return True

        env = {
            **os.environ,
            'PYTHONPATH': f'{_PROJECT_ROOT};{_BACKEND}',
            'FLASK_PORT': str(self.ports['flask']),
            'QDRANT_HTTP_PORT': str(self.ports['qdrant_http']),
            'QDRANT_GRPC_PORT': str(self.ports['qdrant_grpc']),
        }
        print(f"  [webview] Starting...")
        proc = subprocess.Popen(
            [_PYTHON, os.path.join(_BACKEND, 'app.py'), '--webview-only'],
            cwd=_PROJECT_ROOT,
            env=env,
        )
        self.procs['webview'] = proc
        print(f"  [webview] Started (PID {proc.pid})")
        return True

    # ── 清理 ──
    def kill_old(self):
        """清理旧进程"""
        print("=== Cleaning old processes ===")
        r = subprocess.run(
            [_PYTHON, os.path.join(_BASE, 'kill_old.py')],
            cwd=_PROJECT_ROOT,
            timeout=30,
        )
        return r.returncode == 0

    def shutdown(self):
        """优雅退出：按顺序关闭所有子进程（幂等，可多次调用）"""
        if not self._running:
            return
        self._running = False
        print("\n=== Shutting down ===")
        # 顺序: Flask → WebView → Qdrant
        for name in ['flask', 'webview', 'qdrant']:
            proc = self.procs.get(name)
            if proc and proc.poll() is None:
                print(f"  [{name}] Stopping (PID {proc.pid})...")
                try:
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                        capture_output=True, timeout=10,
                    )
                    print(f"  [{name}] Stopped")
                except Exception as e:
                    print(f"  [{name}] Stop failed: {e}")
        print("=== All stopped ===")

    # ── 监控主循环 ──
    def monitor(self):
        """监控子进程，崩溃时自动重启；同时检查文件变更标记重启 Flask"""
        restart_flag = os.path.join(_BACKEND, '.restart_flask')
        _dbg_path = os.path.join(_LOGS_DIR, 'restart_trace.log')
        _loop_count = 0

        with open(_dbg_path, 'a') as _f:
            _f.write(f"[{time.strftime('%H:%M:%S')}] === MONITOR STARTED ===\n")
            _f.write(f"  restart_flag path: {restart_flag}\n")
            _f.write(f"  flag exists now: {os.path.exists(restart_flag)}\n")

        while self._running:
            time.sleep(3)
            _loop_count += 1

            # 每 30s 写一次心跳
            if _loop_count % 10 == 0:
                try:
                    with open(_dbg_path, 'a') as _f:
                        procs_info = {k: (v.pid if v else None) for k, v in self.procs.items()}
                        _f.write(f"[{time.strftime('%H:%M:%S')}] HEARTBEAT loop={_loop_count} running={self._running} procs={procs_info}\n")
                except Exception:
                    pass

            # 检查文件变更重启标记
            flag_exists = os.path.exists(restart_flag)
            if flag_exists:
                try:
                    os.remove(restart_flag)
                    print("  [mgr] Detected Flask restart flag, restarting...")
                    with open(_dbg_path, 'a') as _f:
                        _f.write(f"[{time.strftime('%H:%M:%S')}] *** FLAG DETECTED at loop={_loop_count} ***\n")
                        _f.write(f"  flag removed successfully\n")
                    self.restart_flask()
                    with open(_dbg_path, 'a') as _f:
                        _f.write(f"[{time.strftime('%H:%M:%S')}] restart_flask() returned\n")
                except Exception as e:
                    print(f"  [mgr] Restart flag handling error: {e}")
                    try:
                        with open(_dbg_path, 'a') as _f:
                            _f.write(f"[{time.strftime('%H:%M:%S')}] monitor EXCEPTION in restart: {e}\n")
                    except Exception:
                        pass
            # 检查子进程状态
            for name, proc in list(self.procs.items()):
                if proc.poll() is not None:
                    rc = proc.returncode
                    # webview 正常退出(rc=0) → 整个程序退出
                    if name == 'webview' and rc == 0:
                        print(f"  [webview] Window closed, exiting...")
                        self.shutdown()
                        return
                    # 非正常退出 → 重启
                    print(f"  [{name}] Crashed (exit={rc}), restarting in 3s...")
                    time.sleep(3)
                    if not self._running:
                        return
                    if name == 'flask':
                        self.start_flask()
                    elif name == 'qdrant':
                        self.start_qdrant()
                    elif name == 'webview':
                        self.start_webview()

    # ── 工具方法 ──
    def _is_port_free(self, port):
        """用 socket 试绑定判断端口是否空闲"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            s.close()
            return True
        except OSError:
            return False

    def _is_port_listening(self, port):
        """检查端口是否被监听（反向判断：不空闲 = 被监听）"""
        return not self._is_port_free(port)

    def _wait_url(self, url, timeout=30, label=''):
        """轮询 URL 直到返回 200"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, timeout=3)
                return True
            except Exception:
                time.sleep(1)
        return False

    def _write_qdrant_config(self):
        """生成 Qdrant 配置文件"""
        config_dir = os.path.join(_PROJECT_ROOT, 'qdrant', 'config')
        os.makedirs(config_dir, exist_ok=True)
        with open(_QDRANT_CONFIG, 'w') as f:
            f.write(f"service:\n")
            f.write(f"  host: 0.0.0.0\n")
            f.write(f"  http_port: {self.ports['qdrant_http']}\n")
            f.write(f"  grpc_port: {self.ports['qdrant_grpc']}\n")
            f.write(f"\n")
            f.write(f"storage:\n")
            f.write(f"  storage_path: ./qdrant/storage\n")


# ── 单例锁 ──────────────────────────────────────────
_PM_LOCK_FILE = os.path.join(_BACKEND, '.pm.pid')


def _is_pid_alive(pid):
    """检查进程是否存活（Windows 兼容）"""
    try:
        proc = subprocess.run(
            ['tasklist', '/FI', f'PID eq {pid}', '/NH', '/FO', 'CSV'],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in proc.stdout
    except Exception:
        return False


def _acquire_pm_lock():
    """获取 PM 单例锁：如果已有 PM 在运行则退出"""
    if os.path.exists(_PM_LOCK_FILE):
        try:
            with open(_PM_LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if _is_pid_alive(old_pid):
                print(f"[mgr] Another PM already running (PID {old_pid}), exiting.")
                sys.exit(1)
            else:
                print(f"[mgr] Stale lock from PID {old_pid}, taking over.")
        except (ValueError, OSError):
            pass
    # 写入当前 PID
    with open(_PM_LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    # 注册退出时清理锁文件
    import atexit
    atexit.register(lambda: _release_pm_lock())


def _release_pm_lock():
    """退出时删除锁文件"""
    try:
        if os.path.exists(_PM_LOCK_FILE):
            os.remove(_PM_LOCK_FILE)
    except OSError:
        pass


# ── 入口 ──────────────────────────────────────────────
def main():
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("AiBrain Manager")
    except Exception:
        pass

    # 0. 单例锁 + 清理旧进程
    _acquire_pm_lock()

    parser = argparse.ArgumentParser(description='AiBrain Process Manager')
    parser.add_argument('--no-ui', action='store_true', help='Skip PyWebView (headless mode)')
    args = parser.parse_args()

    pm = ProcessManager(no_ui=args.no_ui)

    # 注册退出信号
    def _sig_handler(sig, frame):
        pm.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    print("=" * 50)
    print("  AiBrain Process Manager")
    print(f"  Flask: {pm.ports['flask']}  Qdrant: {pm.ports['qdrant_http']}/{pm.ports['qdrant_grpc']}")
    print("=" * 50)

    # 1. 清理旧进程（由 start.py 负责调用 kill_old.py）

    # 2. 按顺序启动
    print("\n=== Starting services ===")
    qdrant_ok = pm.start_qdrant()
    if not qdrant_ok:
        print("  [mgr] Qdrant failed to start, waiting 5s before retry...")
        time.sleep(5)
        qdrant_ok = pm.start_qdrant()
        if not qdrant_ok:
            print("  [mgr] FATAL: Qdrant failed to start after retry, aborting.")
            sys.exit(1)
    pm.start_flask()
    pm.start_webview()

    print("\n=== All services running ===")
    print("  Press Ctrl+C to stop all services\n")

    # 3. 监控主循环
    try:
        pm.monitor()
    except KeyboardInterrupt:
        pass
    finally:
        pm.shutdown()


if __name__ == '__main__':
    main()
