"""
独立 Flask 服务进程（由 start.bat 启动，拥有自己的主线程）
支持 watchdog 热重载（不需要 PyWebView 的主线程）
用法: python start_flask.py
"""
import os
import sys
import time

# ── 路径设置 ──
_BASE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..'))
sys.path.insert(0, _BASE)
sys.path.insert(0, _PROJECT_ROOT)

# 端口
_FLASK_PORT = int(os.environ.get('FLASK_PORT', '18980'))

# 强制离线
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import logging
logger = logging.getLogger('flask-server')


def _start_file_watcher():
    """文件变更监控：修改 backend/*.py 后自动重启 Flask 进程

    注意：此功能仅在 FLASK_RELOAD=1 时启用
    """
    reload_enabled = os.environ.get('FLASK_RELOAD', '0') == '1'
    if not reload_enabled:
        return

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    except ImportError:
        logger.info("[hot-reload] watchdog 未安装，跳过")
        return

    watch_dir = _BASE  # backend/ 目录
    _restart_pending = [False]

    class _ReloadHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if isinstance(event, FileModifiedEvent) and event.src_path.endswith('.py'):
                if _restart_pending[0]:
                    return
                rel = os.path.relpath(event.src_path, _PROJECT_ROOT)
                logger.warning(f"[hot-reload] 文件变更: {rel}，2秒后自动重启...")
                _restart_pending[0] = True
                import threading as _th
                _th.Timer(2.0, self._do_restart).start()

        def _do_restart(self):
            logger.warning("[hot-reload] 文件变更，通知 ProcessManager 重启 Flask...")
            # 通过创建标记文件通知 ProcessManager 重启 Flask
            _project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
            restart_flag = os.path.join(_project_root, '.restart_flask')
            try:
                with open(restart_flag, 'w') as f:
                    f.write(str(time.time()))
            except Exception as e:
                logger.error(f"[hot-reload] 写入重启标记失败: {e}")
            # 当前进程退出，由 ProcessManager 检测到后重启
            os._exit(0)

    observer = Observer()
    observer.schedule(_ReloadHandler(), watch_dir, recursive=True)
    observer.daemon = True
    observer.start()
    logger.info(f"[hot-reload] 文件监控已启动: {watch_dir}")


if __name__ == '__main__':
    # 注入 --flask-only 让 app.py 的日志使用 flask_ 前缀
    if '--flask-only' not in sys.argv:
        sys.argv.append('--flask-only')

    # 导入 app（会触发所有模块注册）
    from app import app, _ready, _preload

    # 启动预加载
    threading = __import__('threading')
    threading.Thread(target=_preload, daemon=True).start()

    # 启动文件监控
    _start_file_watcher()

    # ── 设置进程标题（任务管理器可识别）───────────────
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(
            f"AiBrain-Flask :{_FLASK_PORT}"
        )
    except Exception:
        pass

    print(f"[Flask Server] Starting on http://127.0.0.1:{_FLASK_PORT}")

    reload_enabled = os.environ.get('FLASK_RELOAD', '0') == '1'
    if reload_enabled:
        print(f"[Flask Server] Hot-reload: ON (use_reloader=True)")
        app.run(
            host='127.0.0.1',
            port=_FLASK_PORT,
            debug=False,
            use_reloader=True,
            reloader_interval=1,
        )
    else:
        print(f"[Flask Server] use_reloader=False (managed by ProcessManager)")
        app.run(
            host='127.0.0.1',
            port=_FLASK_PORT,
            debug=False,
            use_reloader=False,
        )
