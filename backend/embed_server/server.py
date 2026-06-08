"""
Embedding 独立服务 — BGE-M3 语义模型

加载 BGE-M3 模型常驻内存，通过 HTTP API 提供文本向量化服务。
主 Flask 及 mem0 等其他进程通过 HTTP 调用本服务，避免重复加载模型。

启动方式:
  python backend/embed_server/server.py [--port 19402]
"""
import os
import sys
import argparse

# ── 路径设置 ──────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))           # backend/embed_server/
_BACKEND = os.path.normpath(os.path.join(_BASE, '..'))        # backend/
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..', '..'))  # 项目根

sys.path.insert(0, _BACKEND)
sys.path.insert(0, _PROJECT_ROOT)

# 强制离线
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from flask import Flask, jsonify, request
from flask_cors import CORS

# ── 日志（独立文件 + 归档旧日志） ──────────────────────
import logging
import time as _time

log_dir = os.path.join(_PROJECT_ROOT, 'logs')
os.makedirs(log_dir, exist_ok=True)

# 归档旧的 embed 日志（保留最新 3 份）
from core.logger import archive_logs
archive_logs(log_dir, prefix="embed", keep=3)

log_file = os.path.join(log_dir, f'embed_{_time.strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler(log_file, encoding='utf-8')],
    force=True,
)

logger = logging.getLogger('embed_server')
logger.info(f"Log file: {log_file}")

# ── Flask 应用 ────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# 全局模型引用
_model = None
_model_device = None


def _load_model():
    """后台加载 BGE-M3 模型"""
    global _model, _model_device
    try:
        import torch
        from sentence_transformers import SentenceTransformer

        model_path = os.path.join(_PROJECT_ROOT, 'models', 'bge-m3')
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading BGE-M3 from {model_path} on device: {device}")
        _model = SentenceTransformer(model_path, device=device, local_files_only=True)
        _model_device = device
        logger.info("BGE-M3 model loaded successfully")
        return True
    except Exception as e:
        logger.error(f"BGE-M3 model load failed: {e}")
        return False


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "model_ready": _model is not None,
        "device": _model_device,
    })


@app.route('/ready', methods=['GET'])
def ready():
    """就绪检查（等待模型加载完成）"""
    if _model is not None:
        return jsonify({"ready": True, "device": _model_device})
    return jsonify({"ready": False}), 503


@app.route('/encode', methods=['POST'])
def encode():
    """文本向量化

    Request:  {"texts": ["...", "..."]}
    Response: {"vectors": [[0.1, ...], ...], "dim": 1024}
    """
    if _model is None:
        return jsonify({"error": "model not ready"}), 503

    data = request.get_json() or {}
    texts = data.get("texts", [])
    if not texts:
        return jsonify({"error": "empty texts"}), 400

    try:
        logger.info(f"[encode] encoding {len(texts)} texts")
        embeddings = _model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        vectors = embeddings.tolist()
        logger.info(f"[encode] done: {len(vectors)} vectors, dim={len(vectors[0]) if vectors else 0}")
        return jsonify({
            "vectors": vectors,
            "dim": len(vectors[0]) if vectors else 0,
            "count": len(vectors),
        })
    except Exception as e:
        logger.error(f"encode failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── 启动 ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Embedding Service')
    parser.add_argument('--port', type=int, default=None,
                        help='监听端口（默认从 .port_config 读取第5位）')
    args = parser.parse_args()

    port = args.port
    if port is None:
        config_path = os.path.join(_PROJECT_ROOT, '.port_config')
        try:
            with open(config_path, 'r') as f:
                parts = f.read().strip().split(',')
            if len(parts) >= 5:
                port = int(parts[4].strip())
        except Exception:
            pass
    if port is None:
        port = 19402

    logger.info(f"embed server starting on port {port}...")

    # 后台加载模型
    import threading
    threading.Thread(target=_load_model, daemon=True).start()

    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
