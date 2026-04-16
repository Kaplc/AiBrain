"""纯 Flask 服务器 - 用于测试"""
import os
import sys
import threading
import time

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BASE, 'backend'))

os.environ.setdefault('QDRANT_EMBEDDING_MODEL', os.path.join(_BASE, 'models', 'bge-m3'))
os.environ.setdefault('QDRANT_EMBEDDING_DIM', '1024')
os.environ.setdefault('QDRANT_EXE_PATH', os.path.join(_BASE, 'backend', 'qdrant', 'qdrant.exe'))
os.environ.setdefault('FORCE_CPU', '1')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__, static_folder=os.path.join(_BASE, 'web'), static_url_path='')
CORS(app)

# 模拟 ready_state
_ready = {"model": True, "qdrant": True, "device": "cpu"}

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/status')
def status():
    from brain_mcp.config import settings
    return jsonify({
        "model_loaded": _ready["model"],
        "qdrant_ready": _ready["qdrant"],
        "device": _ready["device"],
        "cuda_available": False,
        "gpu_name": None,
        "embedding_model": "bge-m3",
        "embedding_dim": 1024,
        "model_size": "568M",
        "qdrant_host": settings.qdrant_host,
        "qdrant_port": settings.qdrant_port,
        "qdrant_collection": settings.collection_name,
        "qdrant_top_k": settings.top_k,
    })

@app.route('/chart-data')
def chart_data():
    import datetime as dt
    range_type = __import__('flask').request.args.get('range', 'week')
    today = dt.date.today()

    if range_type == 'week':
        # 生成7天数据
        data = []
        for i in range(6, -1, -1):
            date = today - dt.timedelta(days=i)
            data.append({
                "date": date.isoformat(),
                "added": 0,
                "deleted": 0,
                "total": 0
            })
        return jsonify({"range": range_type, "data": data})
    elif range_type == 'month':
        # 生成30天数据
        data = []
        for i in range(29, -1, -1):
            date = today - dt.timedelta(days=i)
            data.append({
                "date": date.isoformat(),
                "added": 0,
                "deleted": 0,
                "total": 0
            })
        return jsonify({"range": range_type, "data": data})
    elif range_type == 'today':
        # 生成到当前小时的数据
        import datetime as dt
        current_hour = dt.datetime.now().hour
        data = []
        for h in range(current_hour + 1):
            data.append({
                "date": f"{h:02d}:00",
                "added": 0,
                "deleted": 0,
                "total": 0
            })
        return jsonify({"range": range_type, "data": data})
    else:
        return jsonify({"range": range_type, "data": []})

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if __import__('flask').request.method == 'POST':
        return jsonify({"ok": True})
    return jsonify({"device": "cpu"})

@app.route('/db-status')
def db_status():
    return jsonify({"ok": True, "records": 0})

@app.route('/system-info')
def system_info():
    return jsonify({
        "cpu_percent": 10.0,
        "memory_total": 17179869184,
        "memory_used": 8589934592,
        "memory_percent": 50.0,
        "platform": "Windows-10"
    })

@app.route('/store', methods=['POST'])
def store():
    return jsonify({"ok": True, "id": "test-id"})

@app.route('/search', methods=['POST'])
def search():
    return jsonify({"results": [{"id": "test-id", "text": "测试", "score": 0.9}]})

@app.route('/list', methods=['POST'])
def list_memories():
    return jsonify({"memories": []})

@app.route('/log', methods=['POST'])
def log():
    return jsonify({"ok": True})

@app.route('/memory-count', methods=['GET'])
def memory_count():
    return jsonify({"count": 0})

if __name__ == '__main__':
    print("Starting server on http://127.0.0.1:18765")
    app.run(host='127.0.0.1', port=18765, debug=False, use_reloader=False)
