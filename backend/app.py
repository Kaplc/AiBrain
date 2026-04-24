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
logger = setup_logger(_PROJECT_ROOT)

from core.database import StatsDB
stats_db = StatsDB(os.path.join(_BASE, 'stats.db'))

from core.settings import SettingsManager
settings_mgr = SettingsManager(os.path.join(_BASE, 'settings.json'))

from core.model import ModelManager
_ready = {"model": False, "qdrant": False, "device": "unknown"}
model_mgr = ModelManager(_ready, settings_mgr, logger)

app = Flask(__name__, static_folder=os.path.join(_PROJECT_ROOT, 'web'), static_url_path='')
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
        pattern = os.path.join(log_dir, 'app_*.log')
        files = glob.glob(pattern)
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


# ── 预加载（模型 + Qdrant）────────────────────────────────

def _preload():
    import time, urllib.request
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
    app.run(host='127.0.0.1', port=_FLASK_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    # ── 写入 .port 文件（供 start.bat 单例检测用）───────
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

    # 等待 Flask 就绪
    import urllib.request, time
    logger.info('Waiting for Flask to be ready...')
    for _ in range(30):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{_FLASK_PORT}/health', timeout=2)
            logger.info(f'Flask is ready on port {_FLASK_PORT}')
            break
        except Exception:
            time.sleep(0.5)
    else:
        logger.error('Flask failed to start')

    # 等待 Qdrant 就绪（_preload 在后台线程中连接）
    logger.info('Waiting for Qdrant...')
    for _ in range(30):
        if _ready.get("qdrant"):
            logger.info('Qdrant is ready')
            break
        time.sleep(1)
    else:
        logger.error('Qdrant not ready after 30s, aborting startup')
        print('ERROR: Qdrant connection failed. Please check Qdrant configuration.')
        input('Press Enter to exit...')
        os._exit(1)

    ui_path = os.path.join(os.path.dirname(__file__), '..', 'web', 'index.html')
    project_name = os.path.basename(_PROJECT_ROOT)
    import webbrowser

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

    # 窗口关闭时清理
    def on_window_close():
        logger.info('Window closed, shutting down...')
        try:
            _pf = os.path.join(_PROJECT_ROOT, '.port')
            if os.path.exists(_pf):
                os.remove(_pf)
                logger.info("Port file cleaned up")
        except Exception:
            pass

        # 关闭 Qdrant 进程
        import subprocess
        try:
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{_QDRANT_HTTP_PORT}' in line and 'LISTENING' in line:
                    pid = int(line.strip().split()[-1])
                    subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                   capture_output=True, timeout=5)
                    logger.info(f"Qdrant process (PID {pid}) terminated")
                    break
        except Exception as e:
            logger.warning(f"Failed to stop Qdrant: {e}")

        os._exit(0)

    window.events.closed += on_window_close
    webview.start(debug=os.environ.get('WEBVIEW_DEBUG', '0') == '1')
