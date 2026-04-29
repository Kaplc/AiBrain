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
        """重启 Flask 服务（供文件监控调用）"""
        print(f"  [flask] Restarting...")
        # 1. 先杀已记录的进程
        proc = self.procs.get('flask')
        if proc and proc.poll() is None:
            try:
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                    capture_output=True, timeout=10,
                )
            except Exception as e:
                print(f"  [flask] Stop failed: {e}")
        # 2. 再用端口强杀，确保所有残留进程被清除
        flask_port = self.ports['flask']
        try:
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{flask_port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    pid_str = parts[-1]
                    try:
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', pid_str],
                            capture_output=True, timeout=5,
                        )
                        print(f"  [flask] Port-killed residual PID {pid_str}")
                    except Exception:
                        pass
        except Exception:
            pass
        # 3. 等端口释放后再启动
        time.sleep(1)
        return self.start_flask()

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

    def start_file_watcher(self):
        """监控 backend/*.py 变更，自动重启 Flask（需要 watchdog）"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent
        except ImportError:
            print("  [hot-reload] watchdog 未安装，跳过（pip install watchdog 启用）")
            return

        import threading as _threading

        watch_dir = _BACKEND
        _launcher_dir = os.path.normcase(os.path.abspath(_BASE))
        _lock = _threading.Lock()
        _pending = [False]

        mgr = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not isinstance(event, FileModifiedEvent):
                    return
                if not event.src_path.endswith('.py'):
                    return
                # 排除 launcher/ 目录（启动管理脚本不触发重载）
                if os.path.normcase(os.path.abspath(event.src_path)).startswith(_launcher_dir):
                    return
                with _lock:
                    if _pending[0]:
                        return
                    _pending[0] = True
                rel = os.path.relpath(event.src_path, _PROJECT_ROOT)
                print(f"  [hot-reload] 🔄 {rel} 已修改，2秒后重启 Flask...")
                def _do():
                    time.sleep(2)
                    mgr.restart_flask()
                    with _lock:
                        _pending[0] = False
                _threading.Thread(target=_do, daemon=True).start()

        observer = Observer()
        observer.schedule(_Handler(), watch_dir, recursive=True)
        observer.start()
        print(f"  [hot-reload] ✅ 文件监控已启动: backend/ （改.py自动重启）")

    # ── 监控主循环 ──
    def monitor(self):
        """监控子进程，崩溃时自动重启；同时检查文件变更标记重启 Flask"""
        restart_flag = os.path.join(_PROJECT_ROOT, '.restart_flask')
        while self._running:
            time.sleep(3)
            # 检查文件变更重启标记
            if os.path.exists(restart_flag):
                try:
                    os.remove(restart_flag)
                    print("  [mgr] Detected Flask restart flag, restarting...")
                    self.restart_flask()
                except Exception as e:
                    print(f"  [mgr] Restart flag handling error: {e}")
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
    def _is_port_listening(self, port):
        """检查端口是否被监听"""
        try:
            r = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=5
            )
            return f':{port}' in r.stdout and 'LISTENING' in r.stdout
        except Exception:
            return False

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


# ── 入口 ──────────────────────────────────────────────
def main():
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

    # 1. 清理旧进程
    pm.kill_old()

    # 2. 按顺序启动
    print("\n=== Starting services ===")
    pm.start_qdrant()
    pm.start_flask()
    pm.start_webview()
    pm.start_file_watcher()

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
