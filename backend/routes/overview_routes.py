"""Overview 路由 - 模型/Qdrant/Flask/系统状态卡片（纯转发）
提供各状态卡片的详细数据：模型状态、Qdrant 状态、Flask 状态、系统信息"""
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

    @app.route('/overview/model', methods=['GET'])
    def overview_model():
        model_info = _sys_mgr.get_model_info()
        import torch
        return jsonify({
            "loaded": ready_state["model"],
            "device": ready_state["device"],
            "embedding_model": model_info["name"],
            "embedding_dim": int(os.environ.get('QDRANT_EMBEDDING_DIM', '1024')),
            "model_size": model_info["size"],
            "cuda_available": torch.cuda.is_available(),
            "gpu_hardware": _sys_mgr.has_nvidia_gpu(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        })

    @app.route('/overview/qdrant', methods=['GET'])
    def overview_qdrant():
        qdrant_info = _sys_mgr.get_qdrant_info(settings, project_root, logger)
        return jsonify({
            "ready": ready_state["qdrant"],
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "collection": settings.collection_name,
            "top_k": settings.top_k,
            "disk_size": qdrant_info.get("disk_size", 0),
            "storage_path": qdrant_info.get("storage_path", ""),
        })

    @app.route('/overview/flask', methods=['GET'])
    def overview_flask():
        return jsonify({
            "pid": os.getpid(),
            "port": int(os.environ.get('FLASK_PORT', '19398')),
            "uptime": _sys_mgr.get_flask_uptime(),
            "reload": os.environ.get('FLASK_RELOAD', '0') == '1',
        })

    @app.route('/overview/system-info', methods=['GET'])
    def system_info():
        return jsonify(_sys_mgr.get_system_info())

    @app.route('/overview/flask/restart', methods=['POST'])
    def flask_restart():
        try:
            flag = _sys_mgr.write_restart_flag(project_root)
            logger.warning("[flask-restart] 手动重启请求，已写入标志文件")
            return jsonify({"ok": True, "msg": "重启中...", "flag": flag})
        except Exception as e:
            logger.error(f"[flask-restart] 重启失败: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/overview/db-status', methods=['GET'])
    def db_status():
        try:
            st = stats_db.status()
            return jsonify({"ok": True, **st})
        except Exception as e:
            logger.error(f"[db-status] error: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/overview/model-info', methods=['GET'])
    def model_info():
        from brain_mcp import embedding as emb
        import huggingface_hub
        model_name = emb.get_model_name()
        models_local = os.path.join(project_root, 'models')
        local_path = os.path.join(models_local, model_name.replace('/', '_'))
        local_exists = os.path.isdir(local_path) and any(
            f.endswith(('.bin', '.safetensors', '.txt'))
            for f in os.listdir(local_path) if os.path.isfile(os.path.join(local_path, f))
        )
        cache_info = huggingface_hub.scan_cache_dir()
        cached = any(
            'BAAI' in str(m.model_id) or 'bge' in str(m.model_id).lower()
            for m in cache_info.models
        )
        return jsonify({
            "local_models_dir": models_local,
            "model_name": model_name,
            "local_path": local_path if local_exists else None,
            "local_available": local_exists,
            "hf_cache_available": cached,
            "embedding_dim": int(os.environ.get('QDRANT_EMBEDDING_DIM', '1024')),
        })

    @app.route('/overview/frontend/build', methods=['POST'])
    def frontend_build():
        """触发前端构建"""
        import subprocess
        web_dir = os.path.join(project_root, 'web')
        logger.info(f"[build] 开始构建前端，cwd={web_dir}")
        try:
            result = subprocess.run(
                ['npm.cmd', 'run', 'build'],
                cwd=web_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            logger.info(f"[build] returncode={result.returncode}")
            if result.returncode == 0:
                logger.info("[build] 前端构建成功")
                return jsonify({"ok": True, "msg": "构建成功"})
            else:
                stdout_msg = (result.stdout or '')[:500]
                stderr_msg = (result.stderr or '')[:500]
                logger.error(f"[build] 前端构建失败 stdout: {stdout_msg}")
                logger.error(f"[build] 前端构建失败 stderr: {stderr_msg}")
                return jsonify({"ok": False, "error": stderr_msg or stdout_msg or "构建失败"})
        except Exception as e:
            import traceback
            logger.error(f"[build] 前端构建异常: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)})