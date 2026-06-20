"""Brain 路由 — /brain/*（常驻生命循环 + run 观测）

  POST /brain/life/start   启动 LifeLoopDaemon
  POST /brain/life/stop    停止 LifeLoopDaemon
  POST /brain/life/tick    手动触发一次 tick（调试）
  GET  /brain/state        LifeState + config 摘要
  GET  /brain/runs/recent  最近 reactive/background run 摘要
  GET  /brain/runs/<run_id> 单个 run 完整轨迹
"""
from __future__ import annotations

import json

from flask import request, jsonify


def register(app, ready_state, logger, stats_db):
    @app.route('/brain/life/start', methods=['POST'])
    def brain_life_start():
        try:
            from main_brain import get_life_loop_daemon
            d = get_life_loop_daemon()
            res = d.start()
            return jsonify(res)
        except Exception as e:
            logger.warning(f"[brain] life/start failed: {e}")
            return jsonify({"ok": False, "status": "error", "error": str(e)}), 500

    @app.route('/brain/life/stop', methods=['POST'])
    def brain_life_stop():
        try:
            from main_brain import get_life_loop_daemon
            d = get_life_loop_daemon()
            return jsonify(d.stop())
        except Exception as e:
            logger.warning(f"[brain] life/stop failed: {e}")
            return jsonify({"ok": False, "status": "error", "error": str(e)}), 500

    @app.route('/brain/life/tick', methods=['POST'])
    def brain_life_tick():
        """手动触发一次 tick（调试）。body: {tick_type, dry_run, activity}"""
        try:
            body = request.get_json(silent=True) or {}
            tick_type = body.get("tick_type", "medium_tick")
            dry_run = bool(body.get("dry_run", False))
            activity = body.get("activity")
            from main_brain import get_life_loop_daemon
            d = get_life_loop_daemon()
            out = d.run_tick(tick_type, dry_run=dry_run, activity_override=activity)
            return jsonify(out)
        except Exception as e:
            logger.warning(f"[brain] life/tick failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/state', methods=['GET'])
    def brain_state():
        """LifeState + config + scheduler 状态摘要。"""
        try:
            from main_brain.adapters.state import get_state_adapter
            from main_brain import get_life_loop_daemon
            from main_brain.config import get_brain_config
            from main_brain.logging.event_log import get_event_log
            cfg = get_brain_config()
            life = get_state_adapter().read_life_state()
            daemon = get_life_loop_daemon()
            elog = get_event_log()
            return jsonify({
                "life_state": life,
                "scheduler_running": daemon.is_running(),
                "config": {
                    "brain_session_enabled": cfg.session_enabled,
                    "life_loop_enabled": cfg.life_loop_enabled,
                    "proactive_contact_enabled": cfg.proactive_enabled,
                    "autonomy_level": cfg.autonomy_level,
                },
                "last_reactive_run_id": elog.last_run_id("reactive"),
                "last_background_run_id": elog.last_run_id("background"),
                "log_path": elog.log_path(),
            })
        except Exception as e:
            logger.warning(f"[brain] state failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/runs/recent', methods=['GET'])
    def brain_runs_recent():
        """最近 run 摘要。query: mode, limit。"""
        try:
            mode = request.args.get("mode")
            limit = int(request.args.get("limit", 20))
            from main_brain.logging.event_log import get_event_log
            return jsonify({"runs": get_event_log().recent_runs(limit=limit, mode=mode)})
        except Exception as e:
            logger.warning(f"[brain] runs/recent failed: {e}")
            return jsonify({"runs": [], "error": str(e)}), 500

    @app.route('/brain/runs/<run_id>', methods=['GET'])
    def brain_run_detail(run_id):
        """单个 run 完整轨迹（不含用户原文长文本，run.to_full 已截断）。"""
        try:
            from main_brain.logging.event_log import get_event_log
            rec = get_event_log().get_run(run_id)
            if rec is None:
                return jsonify({"error": "run not found"}), 404
            return jsonify(rec)
        except Exception as e:
            logger.warning(f"[brain] run detail failed: {e}")
            return jsonify({"error": str(e)}), 500
