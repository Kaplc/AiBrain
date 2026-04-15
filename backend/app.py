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
_PROJECT_ROOT = os.path.normpath(os.path.join(_BASE, '..'))

os.environ.setdefault('QDRANT_EMBEDDING_MODEL', os.path.join(_PROJECT_ROOT, 'models', 'bge-m3'))
os.environ.setdefault('QDRANT_EMBEDDING_DIM', '1024')
os.environ.setdefault('QDRANT_EXE_PATH', os.path.join(_BASE, 'qdrant', 'qdrant.exe'))

# 允许 CPU 模式运行（不强制要求 GPU）
os.environ.setdefault('FORCE_CPU', '0')

# ── 日志配置 ──────────────────────────────────────────────
_log_dir = os.path.join(_PROJECT_ROOT, 'logs')
os.makedirs(_log_dir, exist_ok=True)

import glob, time as _time

def _roll_logs():
    """只保留最新的 1 个日志文件在 logs/，其余全部归档到 archive/"""
    archive_dir = os.path.join(_log_dir, 'archive')
    os.makedirs(archive_dir, exist_ok=True)
    pattern = os.path.join(_log_dir, 'app_*.log')
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    # files[0] = 最新 1 个 → 保留在 logs/
    # files[1:] = 其余全部 → 归档到 archive/
    for i, f in enumerate(files):
        try:
            if i < 1:
                pass  # 保留在 logs/
            else:
                import shutil
                shutil.move(f, os.path.join(archive_dir, os.path.basename(f)))
        except Exception:
            pass

# 每次启动创建新的带时间戳的日志文件
_log_file = os.path.join(_log_dir, f'app_{_time.strftime("%Y%m%d_%H%M%S")}.log')
_roll_logs()

_handler = logging.FileHandler(_log_file, encoding='utf-8')
_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
_handler.setFormatter(_formatter)

_logger = logging.getLogger('memory')
_logger.setLevel(logging.INFO)
_logger.addHandler(_handler)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

logger = _logger

app = Flask(__name__, static_folder=os.path.join(_PROJECT_ROOT, 'web'), static_url_path='')
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
    force_cpu = os.environ.get('FORCE_CPU', '0') == '1'
    if force_cpu:
        return "cpu"
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
    from mcp_qdrant import embedding as emb
    raw = emb.get_model_name() if hasattr(emb, 'get_model_name') else 'BAAI/bge-m3'
    if raw and ('/' in str(raw) or '\\' in str(raw)):
        model_name = str(raw).replace('\\', '/').split('/')[-1]
    else:
        model_name = raw

    # 获取模型参数量
    model_size = ""
    try:
        if emb._model is not None:
            total_params = sum(p.numel() for p in emb._model.parameters())
            if total_params > 1e9:
                model_size = f"{total_params/1e9:.1f}B"
            elif total_params > 1e6:
                model_size = f"{total_params/1e6:.0f}M"
            else:
                model_size = f"{total_params/1e3:.0f}K"
    except Exception:
        pass

    return jsonify({
        "model_loaded": _ready["model"],
        "qdrant_ready": _ready["qdrant"],
        "device": _ready["device"],
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "embedding_model": model_name,
        "embedding_dim": int(os.environ.get('QDRANT_EMBEDDING_DIM', 1024)),
        "model_size": model_size,
    })


@app.route('/system-info', methods=['GET'])
def system_info():
    """获取系统和GPU内存/温度信息"""
    import torch
    import psutil
    import subprocess

    info = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_total": psutil.virtual_memory().total,
        "memory_used": psutil.virtual_memory().used,
        "memory_percent": psutil.virtual_memory().percent,
    }

    # 优先用 pynvml（NVIDIA）
    if torch.cuda.is_available():
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            info["gpu"] = {
                "name": torch.cuda.get_device_name(0),
                "memory_total": mem_info.total,
                "memory_used": mem_info.used,
                "memory_free": mem_info.free,
                "memory_percent": int(mem_info.used / mem_info.total * 100) if mem_info.total > 0 else 0,
                "temperature": temp,
            }
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.warning(f"pynvml GPU info failed: {e}")
            info["gpu"] = None
    else:
        info["gpu"] = None

    # 非 NVIDIA 显卡用 wmic 获取基本信息
    if info["gpu"] is None:
        try:
            result = subprocess.run(
                'wmic path win32_VideoController get name,AdapterRAM /format:csv',
                shell=True, capture_output=True, timeout=5
            )
            # wmic 输出是 GBK 编码
            lines = result.stdout.decode('gbk', errors='ignore').strip().split('\n')
            lines = [l.strip() for l in lines if l.strip()]
            if len(lines) >= 2:
                # 最后一行是实际的显卡信息，格式：Node,AdapterRAM,Name
                parts = lines[-1].split(',')
                if len(parts) >= 3:
                    name = parts[2].strip()
                    vram = 0
                    try:
                        vram = int(parts[1].strip())
                    except:
                        vram = 0
                    info["gpu"] = {
                        "name": name,
                        "memory_total": vram,
                        "memory_used": 0,
                        "memory_free": vram,
                        "memory_percent": 0,
                        "temperature": None,
                    }
        except Exception as e:
            logger.warning(f"wmic GPU info failed: {e}")

    return jsonify(info)


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
    import torch
    data = request.get_json() or {}
    device_setting = data.get('device', _load_settings().get('device', 'auto'))
    _save_settings({"device": device_setting})

    # 检查 GPU 可用性
    warning = None
    if device_setting == "gpu" and not torch.cuda.is_available():
        warning = "选择了 GPU 模式但未安装 GPU 版 PyTorch，请运行: pip install torch --index-url https://download.pytorch.org/whl/cu124"

    # 后台线程重载，立即返回
    threading.Thread(target=_load_model, args=(device_setting,), daemon=True).start()
    return jsonify({
        "result": f"模型重载中，设备: {device_setting})",
        "warning": warning
    })


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


@app.route('/log', methods=['POST'])
def log():
    """接收前端日志"""
    data = request.get_json() or {}
    level = data.get('level', 'info')
    message = data.get('message', '')
    source = data.get('source', 'frontend')
    msg = f"[{source}] {message}"
    if level == 'error':
        logger.error(msg)
    elif level == 'warn':
        logger.warning(msg)
    else:
        logger.info(msg)
    return jsonify({"ok": True})


# ── 启动 ────────────────────────────────────────────────────

def start_flask():
    app.run(host='127.0.0.1', port=18765, debug=False, use_reloader=False)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    # 启动 Flask 后端（非 daemon，等待就绪）
    flask_thread = threading.Thread(target=start_flask, daemon=False)
    flask_thread.start()

    # 等待 Flask 就绪
    import urllib.request
    logger.info('Waiting for Flask to be ready...')
    for _ in range(30):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:18765/health', timeout=2)
            logger.info('Flask is ready')
            break
        except Exception:
            import time
            time.sleep(0.5)
    else:
        logger.error('Flask failed to start')

    # 打开 PyWebView 窗口
    ui_path = os.path.join(os.path.dirname(__file__), '..', 'web', 'index.html')
    window = webview.create_window(
        title='Memory Manager',
        url=f'http://127.0.0.1:18765',
        width=1000,
        height=680,
        min_size=(800, 500),
        background_color='#0f1117',
    )
    webview.start(debug=os.environ.get('WEBVIEW_DEBUG', '0') == '1')
