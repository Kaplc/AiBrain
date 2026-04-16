"""状态相关路由：/status, /system-info, /health, /db-status"""
import os
import platform
import torch
import psutil
import subprocess
from flask import request, jsonify


def register(app, ready_state, logger, stats_db):
    @app.route('/status', methods=['GET'])
    def status():
        from brain_mcp import embedding as emb
        from brain_mcp.config import settings
        model_info = _get_model_info()
        return jsonify({
            "model_loaded": ready_state["model"],
            "qdrant_ready": ready_state["qdrant"],
            "device": ready_state["device"],
            "cuda_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "embedding_model": model_info["name"],
            "embedding_dim": int(os.environ.get('QDRANT_EMBEDDING_DIM', 1024)),
            "model_size": model_info["size"],
            "qdrant_host": settings.qdrant_host,
            "qdrant_port": settings.qdrant_port,
            "qdrant_collection": settings.collection_name,
            "qdrant_top_k": settings.top_k,
        })

    @app.route('/system-info', methods=['GET'])
    def system_info():
        info = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total": psutil.virtual_memory().total,
            "memory_used": psutil.virtual_memory().used,
            "memory_percent": psutil.virtual_memory().percent,
            "platform": platform.platform(),
            "os_name": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
        }
        logger.info(f"[system-info] CPU={info['cpu_percent']}% MEM={info['memory_used']/1024**3:.1f}/{info['memory_total']/1024**3:.1f}GB OS={info['platform']}")

        # pynvml (NVIDIA)
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
                logger.warning(f"[system-info] pynvml failed: {e}")
                info["gpu"] = None
        else:
            info["gpu"] = None

        # 非 NVIDIA 用 wmic
        if info["gpu"] is None:
            try:
                result = subprocess.run(
                    'wmic path win32_VideoController get name,AdapterRAM /format=csv',
                    shell=True, capture_output=True, timeout=5
                )
                lines = result.stdout.decode('utf-8', errors='ignore').strip().split('\n')
                lines = [l.strip() for l in lines if l.strip()]
                if len(lines) >= 2:
                    parts = lines[-1].split(',')
                    if len(parts) >= 3:
                        name, vram = parts[2].strip(), 0
                        try:
                            vram = int(parts[1].strip())
                        except:
                            pass
                        info["gpu"] = {
                            "name": name,
                            "memory_total": vram,
                            "memory_used": 0,
                            "memory_free": vram,
                            "memory_percent": 0,
                            "temperature": None
                        }
            except Exception as e:
                logger.warning(f"[system-info] wmic failed: {e}")

        return jsonify(info)

    @app.route('/db-status', methods=['GET'])
    def db_status():
        try:
            st = stats_db.status()
            return jsonify({"ok": True, **st})
        except Exception as e:
            logger.error(f"[db-status] error: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/memory-count', methods=['GET'])
    def memory_count():
        """获取记忆总数（从数据库读取，启动时已同步 Qdrant）"""
        try:
            count = stats_db.get_memory_count()
            return jsonify({"count": count})
        except Exception as e:
            logger.error(f"[memory-count] error: {e}")
            return jsonify({"count": 0, "error": str(e)})

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok"})


def _get_model_info():
    from brain_mcp import embedding as emb
    raw = emb.get_model_name() if hasattr(emb, 'get_model_name') else 'BAAI/bge-m3'
    name = raw.replace('\\', '/').split('/')[-1] if raw and ('/' in str(raw) or '\\' in str(raw)) else raw
    size = ""
    try:
        if emb._model is not None:
            total_params = sum(p.numel() for p in emb._model.parameters())
            if total_params > 1e9:
                size = f"{total_params/1e9:.1f}B"
            elif total_params > 1e6:
                size = f"{total_params/1e6:.0f}M"
            else:
                size = f"{total_params/1e3:.0f}K"
    except Exception:
        pass
    return {"name": name, "size": size}


def _get_qdrant_count(settings):
    """获取 Qdrant 集合中的记忆数量"""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        collection_info = client.get_collection(settings.collection_name)
        return collection_info.points_count
    except Exception:
        return 0
