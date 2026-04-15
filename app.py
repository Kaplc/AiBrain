"""
Memory Manager - PyWebView 前端入口
直接调用 mcp_qdrant 业务逻辑，不走 MCP 协议
"""
import os
import sys
import threading
import logging
import webview
from flask import Flask, request, jsonify
from flask_cors import CORS

# 强制离线，防止联网检查模型更新
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 模型路径（本地）
_BASE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('QDRANT_EMBEDDING_MODEL', os.path.join(_BASE, 'models', 'bge-m3'))
os.environ.setdefault('QDRANT_EMBEDDING_DIM', '1024')
os.environ.setdefault('QDRANT_EXE_PATH', r'C:\Users\v_zhyyzheng\Desktop\qdrant\qdrant.exe')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='ui', static_url_path='')
CORS(app)


@app.route('/')
def index():
    return app.send_static_file('index.html')

# ── 预加载状态 ──────────────────────────────────────────────
_ready = {"model": False, "qdrant": False}


def _preload():
    try:
        from mcp_qdrant.tools import get_client
        get_client()
        _ready["qdrant"] = True
        logger.info("Qdrant connected")
    except Exception as e:
        logger.error(f"Qdrant connect failed: {e}")
    try:
        from mcp_qdrant.embedding import load_sentence_transformer
        m = load_sentence_transformer()
        _ready["model"] = m is not None
        logger.info(f"Model loaded: {_ready['model']}")
    except Exception as e:
        logger.error(f"Model load failed: {e}")


threading.Thread(target=_preload, daemon=True).start()


# ── API 路由 ────────────────────────────────────────────────

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "model_loaded": _ready["model"],
        "qdrant_ready": _ready["qdrant"],
    })


@app.route('/store', methods=['POST'])
def store():
    data = request.get_json()
    text = (data or {}).get('text', '').strip()
    if not text:
        return jsonify({"error": "内容不能为空"})
    try:
        from mcp_qdrant.tools import store_memory
        result = store_memory(text)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = (data or {}).get('query', '').strip()
    if not query:
        return jsonify({"results": []})
    try:
        from mcp_qdrant.tools import search_memory
        results = search_memory(query)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e), "results": []})


@app.route('/list', methods=['POST'])
def list_memories():
    try:
        from mcp_qdrant.tools import list_memories as _list
        memories = _list()
        return jsonify({"memories": memories})
    except Exception as e:
        return jsonify({"error": str(e), "memories": []})


@app.route('/delete', methods=['POST'])
def delete():
    data = request.get_json()
    memory_id = (data or {}).get('memory_id', '').strip()
    if not memory_id:
        return jsonify({"error": "缺少 memory_id"})
    try:
        from mcp_qdrant.tools import delete_memory
        result = delete_memory(memory_id)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── 启动 ────────────────────────────────────────────────────

def start_flask():
    app.run(host='127.0.0.1', port=18765, debug=False, use_reloader=False)


if __name__ == '__main__':
    # 启动 Flask 后端（后台线程）
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # 打开 PyWebView 窗口
    ui_path = os.path.join(os.path.dirname(__file__), 'ui', 'index.html')
    window = webview.create_window(
        title='Memory Manager',
        url=f'http://127.0.0.1:18765',
        width=1000,
        height=680,
        min_size=(800, 500),
        background_color='#0f1117',
    )
    webview.start(debug=False)
