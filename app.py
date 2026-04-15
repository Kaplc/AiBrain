"""
Memory Manager - PyWebView 前端入口
直接调用 mcp_qdrant 业务逻辑，不走 MCP 协议
"""
import os
import sys
import json
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
_ready = {"model": False, "qdrant": False, "device": "unknown"}

_SETTINGS_FILE = os.path.join(_BASE, 'settings.json')


def _load_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"device": "cpu"}  # 默认 CPU


def _save_settings(data: dict):
    with open(_SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def _get_device(setting: str) -> str:
    """根据设置解析实际 device"""
    import torch
    if setting == "gpu":
        return "cuda" if torch.cuda.is_available() else "cpu"
    elif setting == "cpu":
        return "cpu"
    else:  # auto
        return "cuda" if torch.cuda.is_available() else "cpu"


def _load_model(device_setting: str = None):
    """加载/重新加载模型"""
    from mcp_qdrant import embedding as emb
    import torch

    if device_setting is None:
        device_setting = _load_settings().get("device", "cpu")

    device = _get_device(device_setting)
    logger.info(f"Loading model on device: {device} (setting={device_setting})")

    _ready["model"] = False
    _ready["device"] = device

    # 显式释放旧模型显存
    if emb._model is not None:
        try:
            # 先把模型移回 CPU，再删除，强制释放 GPU 显存
            emb._model.to('cpu')
            # 遍历子模块确保全部移走
            for p in emb._model.parameters():
                p.data = p.data.cpu()
        except Exception:
            pass
        del emb._model
        emb._model = None
        emb._model_name = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info(f"GPU VRAM released, free: {torch.cuda.memory_reserved(0)//1024//1024}MB reserved")

    from sentence_transformers import SentenceTransformer
    try:
        model = SentenceTransformer(
            emb.get_model_name(),
            device=device,
            local_files_only=True
        )
        emb._model = model
        _ready["model"] = True
        logger.info(f"Model loaded successfully on {device}")
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        _ready["model"] = False


def _preload():
    try:
        import urllib.request
        urllib.request.urlopen('http://localhost:6333/healthz', timeout=5)
        _ready["qdrant"] = True
        logger.info("Qdrant connected")
    except Exception as e:
        logger.error(f"Qdrant connect failed: {e}")

    device_setting = _load_settings().get("device", "cpu")
    _load_model(device_setting)


threading.Thread(target=_preload, daemon=True).start()


# ── API 路由 ────────────────────────────────────────────────

@app.route('/status', methods=['GET'])
def status():
    import torch
    return jsonify({
        "model_loaded": _ready["model"],
        "qdrant_ready": _ready["qdrant"],
        "device": _ready["device"],
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    })


@app.route('/settings', methods=['GET'])
def get_settings():
    return jsonify(_load_settings())


@app.route('/settings', methods=['POST'])
def save_settings():
    data = request.get_json() or {}
    settings = _load_settings()
    settings.update({k: v for k, v in data.items() if k in ('device',)})
    _save_settings(settings)
    return jsonify({"result": "已保存"})


@app.route('/reload-model', methods=['POST'])
def reload_model():
    data = request.get_json() or {}
    device_setting = data.get('device', _load_settings().get('device', 'auto'))
    _save_settings({"device": device_setting})
    # 后台线程重载，立即返回
    threading.Thread(target=_load_model, args=(device_setting,), daemon=True).start()
    return jsonify({"result": f"模型重载中，设备: {device_setting})"})


@app.route('/store', methods=['POST'])
def store():
    data = request.get_json()
    text = (data or {}).get('text', '').strip()
    if not text:
        return jsonify({"error": "内容不能为空"})
    try:
        from mcp_qdrant._core import store_memory
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
        from mcp_qdrant._core import search_memory
        results = search_memory(query)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e), "results": []})


@app.route('/list', methods=['POST'])
def list_memories():
    try:
        from mcp_qdrant._core import list_memories as _list
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
        from mcp_qdrant._core import delete_memory
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
