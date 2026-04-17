"""
Memory Manager - PyWebView 前端入口
模块化架构：core/ 通用模块 + modules/ 路由模块
单项目单实例 + 多项目端口隔离（start.bat 自动分配端口）
"""
import os
import sys
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
os.environ.setdefault('QDRANT_EXE_PATH', os.path.join(_BASE, 'qdrant', 'qdrant.exe'))
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


# ── 其他路由 ───────────────────────────────────────────────

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
            count = stats_db.sync_qdrant_count()
            if count is not None:
                logger.info(f"Synced memory count from Qdrant: {count}")
        except Exception as e:
            logger.error(f"Failed to sync qdrant count: {e}")

    device_setting = settings_mgr.load().get("device", "cpu")
    model_mgr.load(device_setting)


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
    window = webview.create_window(
        title=f'Memory Manager - {project_name}',
        url=f'http://127.0.0.1:{_FLASK_PORT}',
        width=1000,
        height=680,
        min_size=(800, 500),
        background_color='#0f1117',
    )

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
        os._exit(0)

    window.events.closed += on_window_close
    webview.start(debug=os.environ.get('WEBVIEW_DEBUG', '0') == '1')
