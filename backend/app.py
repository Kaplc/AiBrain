"""
Memory Manager - PyWebView 前端入口
模块化架构：core/ 通用模块 + modules/ 路由模块
单项目单实例 + 多项目端口隔离（start.bat 自动分配端口）
"""
import os
import sys
import json
import threading
import webview

# 强制离线
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 模型路径
_BASE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..'))
sys.path.insert(0, _BASE)  # 让 core/modules 可被导入
sys.path.insert(0, _PROJECT_ROOT)  # 让 brain_mcp/、rag/ 等可被导入
# mcp_servers 下的子包也可被导入
_MCP_DIR = os.path.join(_PROJECT_ROOT, 'mcp_servers')
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

# ── 端口（由 start.bat 通过环境变量传入）────────────────
_FLASK_PORT = int(os.environ.get('FLASK_PORT', '18765'))
_QDRANT_HTTP_PORT = int(os.environ.get('QDRANT_HTTP_PORT', '6333'))

os.environ.setdefault('QDRANT_EMBEDDING_MODEL', os.path.join(_PROJECT_ROOT, 'models', 'bge-m3'))
os.environ.setdefault('QDRANT_EMBEDDING_DIM', '1024')
os.environ.setdefault('QDRANT_EXE_PATH', os.path.join(_PROJECT_ROOT, 'qdrant', 'qdrant.exe'))
os.environ.setdefault('FORCE_CPU', '0')

from flask import Flask, request, jsonify
from flask_cors import CORS


# ── 初始化 core 模块 ──────────────────────────────────────
from core.logger import setup_logger

# 在 import 前检测进程角色（用于日志文件命名）
_log_role = 'app'
if '--flask-only' in sys.argv:
    _log_role = 'flask'
elif '--webview-only' in sys.argv:
    _log_role = 'ui'

logger = setup_logger(_PROJECT_ROOT, role=_log_role)

from core.database import StatsDB
stats_db = StatsDB(os.path.join(_BASE, 'stats.db'))

from core.settings import SettingsManager
settings_mgr = SettingsManager(os.path.join(_BASE, 'settings.json'))

from core.model import ModelManager
_ready = {"model": False, "qdrant": False, "device": "unknown"}
model_mgr = ModelManager(_ready, settings_mgr, logger)

_dist = os.path.join(_PROJECT_ROOT, 'web', 'dist')
_web = os.path.join(_PROJECT_ROOT, 'web')
# 优先使用构建产物（dist/），不存在时回退到源码目录（开发模式）
_static = _dist if os.path.isdir(_dist) else _web
app = Flask(__name__, static_folder=_static, static_url_path='')
CORS(app)


# ── 注册路由模块 ───────────────────────────────────────────
from modules.status import register as reg_status
reg_status(app, _ready, logger, stats_db)

from modules.memory import register as reg_memory
reg_memory(app, stats_db)

from modules.settings_mod import register as reg_settings
reg_settings(app, settings_mgr, model_mgr)

from modules.stats import register as reg_stats
reg_stats(app, stats_db)

from modules.stream import register as reg_stream
reg_stream(app, stats_db)

from modules.wiki_mod import register as reg_wiki
reg_wiki(app, stats_db)


# ── 其他路由 ───────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/')
def index():
    return app.send_static_file('index.html')


logger.info(f'[spa_fallback] static_folder={app.static_folder}')
# ── SPA fallback: 所有非 API 路由回退到 index.html ──
@app.route('/<path:path>/')
def spa_fallback_slash(path):
    return spa_fallback(path)

@app.route('/<path:path>')
def spa_fallback(path):
    logger.info(f'[spa_fallback] path={path}')
    # 检查是否为静态文件
    static_file = os.path.join(app.static_folder or '', path)
    if os.path.isfile(static_file):
        logger.info(f'[spa_fallback] serving static file: {static_file}')
        return app.send_static_file(path)
    # 返回 index.html
    index_path = os.path.join(app.static_folder or '', 'index.html')
    logger.info(f'[spa_fallback] serving index.html, exists={os.path.isfile(index_path)}')
    with open(index_path, 'rb') as f:
        return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

# 前端路由快捷方式
@app.route('/overview')
@app.route('/settings')
@app.route('/wiki')
@app.route('/console')
@app.route('/memory')
def spa_shortcut():
    from flask import request
    return spa_fallback(request.path.lstrip('/'))


@app.route('/log', methods=['POST'])
def log():
    """接收前端日志"""
    data = request.get_json() or {}
    level = data.get('level', 'info')
    message = data.get('message', '')
    source = data.get('source', 'frontend')
    msg = f"[{source}] {message}"
    if level == 'error': logger.error(msg)
    elif level == 'warn': logger.warning(msg)
    else: logger.info(msg)
    return jsonify({"ok": True})


@app.route('/logs', methods=['GET'])
def get_logs():
    """读取后端日志文件的最后 N 行"""
    import glob
    try:
        log_dir = os.path.join(_PROJECT_ROOT, 'logs')
        files = []
        for pat in ('app_*.log', 'flask_*.log', 'ui_*.log'):
            files.extend(glob.glob(os.path.join(log_dir, pat)))
        if not files:
            return jsonify({"lines": [], "file": None})

        log_file = max(files, key=os.path.getmtime)
        lines_param = request.args.get('lines', '300', type=int)
        lines_param = min(max(lines_param, 10), 1000)

        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        tail = all_lines[-lines_param:] if len(all_lines) > lines_param else all_lines
        return jsonify({
            "lines": [l.rstrip() for l in tail],
            "file": os.path.basename(log_file),
            "total": len(all_lines),
            "returned": len(tail),
        })
    except Exception as e:
        logger.error(f"[API✗] /logs 失败: {e}")
        return jsonify({"error": str(e), "lines": []})


def _get_ui_settings_path():
    """用户目录下的 UI 偏好配置"""
    cfg_dir = os.path.join(os.path.expanduser("~"), ".aibrain", "config")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "ui_settings.json")


def _load_ui_settings() -> dict:
    """加载 UI 设置（不存在则返回默认）"""
    path = _get_ui_settings_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # 默认值
    return {
        "log_auto_refresh": True,
        "log_interval": 3,
    }


@app.route('/ui-settings', methods=['GET', 'POST'])
def ui_settings():
    """读取/保存 UI 偏好设置"""
    if request.method == 'GET':
        return jsonify(_load_ui_settings())

    try:
        data = request.get_json() or {}
        current = _load_ui_settings()

        # 白名单字段，只允许更新已知 key
        allowed_keys = {'log_auto_refresh', 'log_interval'}
        for k in allowed_keys:
            if k in data:
                current[k] = data[k]

        path = _get_ui_settings_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        logger.info("[API←] /ui-settings 已保存")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"[API✗] /ui-settings 失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/console/commands')
def get_console_commands():
    """扫描 web/console 目录，返回所有 cmd_*.js 文件列表"""
    import glob
    try:
        console_dir = os.path.join(_PROJECT_ROOT, 'web', 'console')
        pattern = os.path.join(console_dir, 'cmd_*.js')
        files = glob.glob(pattern)
        # 只返回文件名，按字母排序
        commands = sorted([os.path.basename(f) for f in files])
        return jsonify({"commands": commands})
    except Exception as e:
        logger.error(f"[API✗] /console/commands 失败: {e}")
        return jsonify({"error": str(e), "commands": []})


@app.route('/console/poll', methods=['GET'])
def poll_console_queue():
    """MCP服务器写入的命令队列，供前端轮询"""
    try:
        queue_file = os.path.join(os.path.expanduser("~"), ".aibrain", "console_queue.json")
        if os.path.exists(queue_file):
            try:
                with open(queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return jsonify({"commands": data.get("commands", [])})
            except (json.JSONDecodeError, ValueError):
                # 文件损坏/为空，重置
                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump({"commands": []}, f)
        return jsonify({"commands": []})
    except Exception as e:
        logger.error(f"[API✗] /console/poll 失败: {e}")
        return jsonify({"error": str(e), "commands": []})


@app.route('/console/poll', methods=['POST'])
def clear_console_queue():
    """清空命令队列（前端执行完成后调用）"""
    try:
        queue_file = os.path.join(os.path.expanduser("~"), ".aibrain", "console_queue.json")
        import tempfile
        dir_ = os.path.dirname(queue_file)
        os.makedirs(dir_, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=dir_, delete=False, suffix='.tmp') as tf:
            json.dump({"commands": [], "timestamp": int(time.time())}, tf)
            tmp_path = tf.name
        os.replace(tmp_path, queue_file)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"[API✗] /console/poll(clear) 失败: {e}")
        return jsonify({"error": str(e)})


# ── 预加载（模型 + Qdrant）────────────────────────────────

def _preload():
    import time, urllib.request

    # ── 初始化用户配置目录 ─────────────────────────────────
    from modules.settings_mod import AibrainConfigManager
    AibrainConfigManager.get_instance().init_default_configs()

    # 重试连接 Qdrant（最多 20 秒）
    for attempt in range(10):
        try:
            urllib.request.urlopen(f'http://localhost:{_QDRANT_HTTP_PORT}/healthz', timeout=3)
            _ready["qdrant"] = True
            logger.info(f"Qdrant connected on port {_QDRANT_HTTP_PORT}")
            break
        except Exception as e:
            if attempt < 9:
                time.sleep(2)
            else:
                logger.error(f"Qdrant connect failed after retries: {e}")

    # 同步 Qdrant 记忆数量到数据库
    if _ready["qdrant"]:
        try:
            # 确保 collection 存在
            from modules.brain.memory import get_client
            get_client()
            count = stats_db.sync_qdrant_count()
            if count is not None:
                logger.info(f"Synced memory count from Qdrant: {count}")
        except Exception as e:
            logger.error(f"Failed to sync qdrant count: {e}")

    # 初始化 mem0 客户端
        try:
            from modules.brain.mem0_adapter import get_mem0_client
            get_mem0_client()
            logger.info("mem0 client initialized successfully")
        except Exception as e:
            logger.warning(f"mem0 initialization failed (non-fatal): {e}")

        # 自动迁移旧记忆
        try:
            from modules.brain.migrate import needs_migration, migrate_old_memories
            if needs_migration(_PROJECT_ROOT):
                result = migrate_old_memories(_PROJECT_ROOT)
                if result["error"]:
                    logger.warning(f"Migration error: {result['error']}")
        except Exception as e:
            logger.warning(f"Migration check failed (non-fatal): {e}")

    device_setting = settings_mgr.load().get("device", "cpu")
    model_mgr.load(device_setting)

    # 预热记忆数量缓存（模型加载后 mem0 client 已就绪）
    try:
        from modules.brain.memory import warmup_memory_count
        warmup_memory_count()
    except Exception as e:
        logger.warning(f"warmup_memory_count failed (non-fatal): {e}")

    # 预加载 LightRAG 引擎（避免首次搜索请求时才初始化）
    try:
        from rag.lightrag_wiki.rag_engine import get_rag
        get_rag()
        logger.info("LightRAG preloaded successfully")
    except Exception as e:
        logger.warning(f"LightRAG preload failed (will lazy-init on first search): {e}")


threading.Thread(target=_preload, daemon=True).start()


# ── 启动 ───────────────────────────────────────────────────

def start_flask():
    """Flask 服务

    FLASK_RELOAD=1: use_reloader=True（仅独立使用 start_flask.py 时）
    FLASK_RELOAD=0(默认): use_reloader=False（由 ProcessManager 管理重启）
    """
    _reload = os.environ.get('FLASK_RELOAD', '0') == '1'
    if _reload:
        logger.info("[Flask] Hot-reload: ON (use_reloader=True)")
        app.run(
            host='127.0.0.1',
            port=_FLASK_PORT,
            debug=False,
            use_reloader=True,
            reloader_interval=1,
        )
    else:
        logger.info("[Flask] use_reloader=False (managed by ProcessManager)")
        app.run(
            host='127.0.0.1',
            port=_FLASK_PORT,
            debug=False,
            use_reloader=False,
        )


def _wait_and_start_ui():
    """Bootstrap：等 Flask+Qdrant 就绪后启动 PyWebView 窗口（主线程）"""
    import urllib.request, time as _time

    # 等 Flask 就绪
    logger.info('[bootstrap] Waiting for Flask...')
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{_FLASK_PORT}/health', timeout=2)
            logger.info(f'[bootstrap] Flask ready on {_FLASK_PORT}')
            break
        except Exception:
            _time.sleep(0.5)
    else:
        logger.error('[bootstrap] Flask failed to start')
        os._exit(1)

    # 等 Qdrant 就绪
    logger.info('[bootstrap] Waiting for Qdrant...')
    for _ in range(30):
        if _ready.get("qdrant"):
            logger.info('[bootstrap] Qdrant ready')
            break
        _time.sleep(1)
    else:
        logger.warning('[bootstrap] Qdrant not ready after 30s, continuing')

    # 启动 PyWebView（必须在主线程！）
    import webbrowser

    ui_path = os.path.join(os.path.dirname(__file__), '..', 'web', 'index.html')
    project_name = os.path.basename(_PROJECT_ROOT)

    window = webview.create_window(
        title=f'Memory Manager - {project_name}',
        url=f'http://127.0.0.1:{_FLASK_PORT}',
        width=1000,
        height=680,
        min_size=(800, 500),
        background_color='#0f1117',
    )

    def open_in_browser():
        webbrowser.open(f'http://127.0.0.1:{_FLASK_PORT}')

    window.expose(open_in_browser)

    def on_window_close():
        logger.info('Window closed, shutting down...')
        try:
            _pf = os.path.join(_PROJECT_ROOT, '.port')
            if os.path.exists(_pf):
                os.remove(_pf)
        except Exception:
            pass
        import subprocess
        try:
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if f':{_QDRANT_HTTP_PORT}' in line and 'LISTENING' in line:
                    pid = int(line.strip().split()[-1])
                    subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                   capture_output=True, timeout=5)
                    break
        except Exception as e:
            logger.warning(f"Failed to stop Qdrant: {e}")
        os._exit(0)

    window.events.closed += on_window_close

    # ── 设置进程标题（任务管理器可识别）───────────────
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(
            f"AiBrain-UI :{_FLASK_PORT}"
        )
    except Exception:
        pass

    # 阻塞主线程 — PyWebView 必须在主线程
    webview.start(debug=os.environ.get('WEBVIEW_DEBUG', '0') == '1')


if __name__ == '__main__':
    import argparse
    try:
        import ctypes
        _title = "AiBrain Flask" if '--flask-only' in sys.argv else "AiBrain WebView" if '--webview-only' in sys.argv else "AiBrain"
        ctypes.windll.kernel32.SetConsoleTitleW(_title)
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument('--webview-only', action='store_true',
                        help='只启动 PyWebView 窗口（Flask 由独立进程启动）')
    parser.add_argument('--flask-only', action='store_true',
                        help='只启动 Flask 服务（不启动窗口，用于 start.bat 双进程模式）')
    args = parser.parse_args()

    if args.flask_only:
        logger.info(f"[Flask-Only] Starting on port {_FLASK_PORT}")
        start_flask()

    elif args.webview_only:
        # ── WebView-only 模式：主线程跑 PyWebView ─────────
        _wait_and_start_ui()

    else:
        # ── 兼容旧的单进程模式：Flask子线程 + WebView主线程 ─
        _port_file = os.path.join(_PROJECT_ROOT, '.port')
        try:
            with open(_port_file, 'w') as pf:
                pf.write(str(_FLASK_PORT))
            logger.info(f"Port file written: {_FLASK_PORT}")
        except Exception as e:
            logger.warning(f"Failed to write port file: {e}")

        logger.info(f"Starting -> Flask:{_FLASK_PORT} Qdrant-HTTP:{_QDRANT_HTTP_PORT}")

        flask_thread = threading.Thread(target=start_flask, daemon=False)
        flask_thread.start()

        _wait_and_start_ui()
