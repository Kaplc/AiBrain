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

    @app.route('/brain/chat/mode', methods=['GET', 'POST'])
    def brain_chat_mode():
        try:
            from main_brain.config import get_brain_config
            bc = get_brain_config()
            if request.method == 'POST':
                body = request.get_json(silent=True) or {}
                mode = body.get('mode', '')
                bc.set_chat_mode(mode)
                logger.info(f'[brain] chat mode set to {mode}')
            return jsonify({'mode': bc.get_chat_mode()})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.warning(f'[brain] chat/mode failed: {e}')
            return jsonify({'error': str(e)}), 500

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

    # ── 输出记忆沉淀（memory consolidation）调试接口 ──────────
    @app.route('/brain/events/ingest', methods=['POST'])
    def brain_events_ingest():
        try:
            body = request.get_json(silent=True) or {}
            source = body.get("source", "system")
            evt_type = body.get("type", "system_signal")
            modality = body.get("modality", "text")
            content = body.get("content", "")
            metadata = body.get("metadata", {})
            from main_brain.contracts import BrainEvent, _new_event_id, _new_trace_id, _now_iso
            from main_brain.orchestrator import Orchestrator
            event = BrainEvent(
                id=_new_event_id(), trace_id=_new_trace_id(),
                source=source, type=evt_type, modality=modality,
                content=content, timestamp=_now_iso(),
                salience=body.get("salience", 0.5), metadata=metadata,
            )
            ctx = Orchestrator.get_instance().process_event(event, max_depth=int(body.get("max_depth", 3)))
            return jsonify({"ok": not bool(ctx.error), "event_id": event.id, "trace_id": event.trace_id, "error": ctx.error or None})
        except Exception as e:
            logger.warning(f"[brain] events/ingest failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/events/recent', methods=['GET'])
    def brain_events_recent():
        try:
            limit = int(request.args.get("limit", 50))
            from main_brain.logging.event_log import get_event_log
            log_path = get_event_log().log_path()
            events = _read_recent_events(log_path, limit)
            return jsonify({"events": events})
        except Exception as e:
            logger.warning(f"[brain] events/recent failed: {e}")
            return jsonify({"events": [], "error": str(e)}), 500

    @app.route('/brain/events/<event_id>', methods=['GET'])
    def brain_event_detail(event_id):
        try:
            from main_brain.logging.event_log import get_event_log
            log_path = get_event_log().log_path()
            events = _read_recent_events(log_path, 500)
            for ev in events:
                if ev.get("id") == event_id:
                    return jsonify(ev)
            return jsonify({"error": "event not found"}), 404
        except Exception as e:
            logger.warning(f"[brain] event detail failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/memory/consolidate', methods=['POST'])
    def brain_memory_consolidate():
        """触发一次输出记忆沉淀。body: {trigger, window_size, dry_run}"""
        try:
            body = request.get_json(silent=True) or {}
            trigger = body.get("trigger", "manual")
            window_size = int(body.get("window_size", 20))
            dry_run = bool(body.get("dry_run", False))
            if window_size <= 0 or window_size > 100:
                return jsonify({"error": "window_size 必须在 1..100"}), 400
            from main_brain.consolidation import consolidate_memory
            return jsonify(consolidate_memory(trigger, dry_run=dry_run, window_size=window_size))
        except Exception as e:
            logger.warning(f"[brain] memory/consolidate failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/memory/consolidate/preview', methods=['POST'])
    def brain_memory_consolidate_preview():
        """dry-run 预览候选+评分，不写库、不推进检查点。body: {trigger, window_size}"""
        try:
            body = request.get_json(silent=True) or {}
            trigger = body.get("trigger", "manual")
            window_size = int(body.get("window_size", 20))
            if window_size <= 0 or window_size > 100:
                return jsonify({"error": "window_size 必须在 1..100"}), 400
            from main_brain.consolidation import preview_memory_consolidation
            return jsonify(preview_memory_consolidation(trigger, window_size=window_size))
        except Exception as e:
            logger.warning(f"[brain] memory/consolidate/preview failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/memory/consolidation/state', methods=['GET'])
    def brain_memory_consolidation_state():
        """沉淀检查点状态。"""
        try:
            from modules.brain.memory.consolidation import get_trace_store
            state = get_trace_store().get_state()
            return jsonify({
                "last_processed_seq": state.last_processed_seq,
                "last_run_id": state.last_run_id,
                "last_saved_at": state.last_saved_at,
                "last_saved_memory_id": state.last_saved_memory_id,
                "policy_version": state.policy_version,
                "cooldown_until": state.cooldown_until,
                "pending_backlog": state.pending_backlog,
                "seen_hash_count": len(state.seen_hashes),
            })
        except Exception as e:
            logger.warning(f"[brain] memory/consolidation/state failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/memory/consolidation/recent', methods=['GET'])
    def brain_memory_consolidation_recent():
        """最近几次沉淀运行摘要（调试/回放）。query: limit。"""
        try:
            limit = int(request.args.get("limit", 10))
            from modules.brain.memory.consolidation import get_trace_store
            return jsonify({"runs": get_trace_store().recent_runs(limit=limit)})
        except Exception as e:
            logger.warning(f"[brain] memory/consolidation/recent failed: {e}")
            return jsonify({"runs": [], "error": str(e)}), 500


# ── 小工具 ───────────────────────────────────────────────────
def _read_recent_events(log_path: str, limit: int = 50) -> list[dict]:
    """从 JSONL 读取最近事件（尾部倒序读）。"""
    import json
    import os
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("id") or rec.get("event_id"):
                events.append(rec)
                if len(events) >= limit:
                    break
        return events
    except Exception:
        return []

