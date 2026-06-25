"""Overview 路由 - 模型/Qdrant/Flask/系统状态卡片（纯转发）
提供各状态卡片的详细数据：模型状态、Qdrant 状态、Flask 状态、系统信息"""
import os
import json
import time
import torch
from flask import jsonify, request
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
        """触发前端构建（后台执行，立即返回 build_id）"""
        import subprocess
        import uuid
        from concurrent.futures import ThreadPoolExecutor

        web_dir = os.path.join(project_root, 'web')
        build_id = str(uuid.uuid4())[:8]

        def _do_build():
            """后台执行构建"""
            logger.info(f"[build:{build_id}] 开始构建前端，cwd={web_dir}")
            try:
                result = subprocess.run(
                    ['npm.cmd', 'run', 'build'],
                    cwd=web_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    stats_db.update_build_status(build_id, 'done', '构建成功')
                    logger.info(f"[build:{build_id}] 前端构建成功")
                else:
                    err = (result.stderr or result.stdout or '构建失败')[:500]
                    stats_db.update_build_status(build_id, 'failed', err)
                    logger.error(f"[build:{build_id}] 前端构建失败: {err}")
            except Exception as e:
                import traceback
                stats_db.update_build_status(build_id, 'failed', str(e))
                logger.error(f"[build:{build_id}] 前端构建异常: {e}\n{traceback.format_exc()}")

        # 后台线程执行，不阻塞
        stats_db.update_build_status(build_id, 'building', '构建中...')
        ThreadPoolExecutor(max_workers=1).submit(_do_build)
        return jsonify({"build_id": build_id, "status": "building"})

    @app.route('/overview/frontend/build/status', methods=['GET'])
    def frontend_build_status():
        """轮询构建状态"""
        build_id = request.args.get('build_id', '')
        if not build_id:
            return jsonify({"error": "缺少 build_id"})
        try:
            status, msg = stats_db.get_build_status(build_id)
            return jsonify({"build_id": build_id, "status": status, "msg": msg})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/overview/balance', methods=['GET'])
    def overview_balance():
        """查询 DeepSeek 账户余额（转发官方 API）"""
        try:
            from core.settings import ConfigManager
            cfg = ConfigManager.get_instance().read_llm()
            api_key = cfg.get('api_key', '')
            base_url = cfg.get('base_url', 'https://api.deepseek.com')

            if not api_key:
                logger.warning("[balance] API key not configured")
                return jsonify({"error": "API key not configured"}), 503
            if 'deepseek' not in base_url.lower():
                logger.warning(f"[balance] not a DeepSeek base URL: {base_url}")
                return jsonify({"error": "not a DeepSeek base URL"}), 400

            import urllib.request
            url = f'{base_url.rstrip("/")}/user/balance'
            logger.info(f"[balance] requesting {url}")
            req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
            logger.info(f"[balance] auth: Bearer {api_key[:8]}...")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            _info_str = "; ".join([f"{b.get('currency','?')}={b.get('total_balance','?')}" for b in data.get('balance_infos', [])])
            logger.info(f"[balance] response: is_available={data.get('is_available')}, infos=[{_info_str}]")
            # 附加今日 Token 消耗费用
            try:
                today_cost = stats_db.get_today_cost()
                data['today_cost'] = today_cost
                logger.info(f"[balance] today_cost=¥{today_cost['total_cost']}")
            except Exception as ec:
                logger.warning(f"[balance] today_cost failed: {ec}")
            return jsonify(data)
        except urllib.error.HTTPError as e:
            logger.warning(f"[balance] HTTP {e.code}: {e.reason}")
            return jsonify({"error": f"DeepSeek API {e.code}: {e.reason}"}), e.code
        except Exception as e:
            logger.warning(f"[balance] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/overview/token-usage', methods=['GET'])
    def token_usage():
        """Token 用量统计（支持预设时间段和自定义范围）

        Query params:
            start: 开始日期 YYYY-MM-DD 或 YYYY-MM-DD HH:MM（可选）
            end:   结束日期（可选，默认当前时间）
        不传参数返回 24h / 7d / 30d 三个预设时间段
        """
        try:
            start = request.args.get('start', '')
            end = request.args.get('end', '')

            if start:
                # 自定义范围
                import datetime as _dt
                try:
                    start_dt = _dt.datetime.strptime(start[:16], '%Y-%m-%d %H:%M')
                except ValueError:
                    start_dt = _dt.datetime.strptime(start[:10], '%Y-%m-%d')
                now = _dt.datetime.now()
                hours = int((now - start_dt).total_seconds() / 3600) + 1
                result = stats_db.get_token_usage_summary(hours=max(1, hours))
                return jsonify({"ok": True, "custom": result})

            # 预设时间段
            return jsonify({
                "ok": True,
                "periods": {
                    "24h": stats_db.get_token_usage_summary(hours=24),
                    "7d": stats_db.get_token_usage_summary(hours=168),
                    "30d": stats_db.get_token_usage_summary(hours=720),
                }
            })
        except Exception as e:
            logger.error(f"[token-usage] error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500