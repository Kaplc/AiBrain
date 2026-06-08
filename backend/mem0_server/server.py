"""
mem0 独立服务入口

启动一个轻量 Flask 服务，持有 mem0 客户端单例（BGE-M3 + Qdrant）。
主 Flask 通过 HTTP API 调用本服务，避免主进程重启时重载语义模型。

启动方式:
  python backend/mem0_server/server.py [--port 19401]
"""
import os
import sys
import argparse

# ── 路径设置 ──────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))        # backend/mem0_server/
_BACKEND = os.path.normpath(os.path.join(_BASE, '..'))     # backend/
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..', '..'))  # 项目根

sys.path.insert(0, _BACKEND)
sys.path.insert(0, _PROJECT_ROOT)

# 强制离线
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from flask import Flask, jsonify
from flask_cors import CORS

# ── 日志（独立文件 + 归档旧日志） ──────────────────────
import logging
import time as _time

log_dir = os.path.join(_PROJECT_ROOT, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 归档旧的 mem0 日志（保留最新 3 份）
from core.logger import archive_logs
archive_logs(log_dir, prefix="mem0", keep=3)

log_file = os.path.join(log_dir, f'mem0_{_time.strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler(log_file, encoding='utf-8')],
    force=True,
)

logger = logging.getLogger('mem0_server')
logger.info(f"Log file: {log_file}")

# ── Flask 应用 ────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# 全局 mem0 客户端（懒初始化）
_client = None


def _get_client():
    """获取 mem0 客户端单例"""
    global _client
    if _client is None:
        from modules.brain.mem0_adapter import _create_client
        _client = _create_client()
        logger.info("mem0 client initialized (server mode)")
    return _client


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    client_ready = _client is not None
    return jsonify({
        "status": "ok",
        "client_ready": client_ready,
    })


@app.route('/ready', methods=['GET'])
def ready():
    """就绪检查（等待客户端初始化完成）"""
    try:
        c = _get_client()
        return jsonify({"ready": True})
    except Exception as e:
        return jsonify({"ready": False, "error": str(e)}), 503


# ── 注册 API 路由 ──────────────────────────────────────
from mem0_server.routes import register_routes
register_routes(app, _get_client, logger)


# ── 启动 ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='mem0 Standalone Service')
    parser.add_argument('--port', type=int, default=None,
                        help='监听端口（默认从 .port_config 读取第4位）')
    args = parser.parse_args()

    port = args.port
    if port is None:
        # 从 .port_config 读取
        config_path = os.path.join(_PROJECT_ROOT, '.port_config')
        try:
            with open(config_path, 'r') as f:
                parts = f.read().strip().split(',')
            if len(parts) >= 4:
                port = int(parts[3].strip())
        except Exception:
            pass
    if port is None:
        port = 19401

    logger.info(f"mem0 server starting on port {port}...")

    # 后台初始化 mem0 客户端
    import threading
    def _init():
        try:
            _get_client()
            logger.info("mem0 client ready")
        except Exception as e:
            logger.error(f"mem0 client init failed: {e}")

    threading.Thread(target=_init, daemon=True).start()

    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
