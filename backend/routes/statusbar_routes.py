"""状态栏路由 - /statusbar/api（纯转发）
返回模型/Qdrant/Flask 实时状态，供前端状态栏展示"""
import os
import time
import torch
from flask import jsonify
from modules.SystemInfo.system_info_mod import SystemInfoManager

_sys_mgr = SystemInfoManager.get_instance()


def register(app, ready_state, logger, stats_db):
    project_root = app.config.get('_PROJECT_ROOT', '')
    _sys_mgr.set_flask_start_time(time.time())

    from brain_mcp.config import settings
    _sys_mgr.init_qdrant_cache(settings, project_root, logger)

    @app.route('/statusbar/api', methods=['GET'])
    def statusbar_api():
        model_info = _sys_mgr.get_model_info()
        cuda_available = torch.cuda.is_available()
        gpu_hardware = _sys_mgr.has_nvidia_gpu()
        qdrant_info = _sys_mgr.get_qdrant_info(settings, project_root, logger)

        return jsonify({
            "model_loaded": ready_state["model"],
            "qdrant_ready": ready_state["qdrant"],
            "device": ready_state["device"],
            "cuda_available": cuda_available,
            "gpu_hardware": gpu_hardware,
            "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
            "embedding_model": model_info["name"],
            "embedding_dim": int(os.environ.get('QDRANT_EMBEDDING_DIM', '1024')),
            "model_size": model_info["size"],
            "qdrant_host": settings.qdrant_host,
            "qdrant_port": settings.qdrant_port,
            "qdrant_collection": settings.collection_name,
            "qdrant_top_k": settings.top_k,
            "qdrant_disk_size": qdrant_info.get("disk_size", 0),
            "qdrant_storage_path": qdrant_info.get("storage_path", ""),
            "flask_port": int(os.environ.get('FLASK_PORT', '18765')),
            "flask_pid": os.getpid(),
            "flask_uptime": _sys_mgr.get_flask_uptime(),
            "flask_reload": os.environ.get('FLASK_RELOAD', '0') == '1',
        })