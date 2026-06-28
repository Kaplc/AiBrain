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

from flask import request, jsonify, Response, stream_with_context


def _get_activity_count() -> int:
    """获取已注册活动数量（惰性加载，失败返回 0）。"""
    try:
        from main_brain.activities.registry import list_activities
        return len(list_activities())
    except Exception:
        return 0


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
        """手动触发一次意识流 tick（调试）。body: {dry_run}"""
        try:
            body = request.get_json(silent=True) or {}
            dry_run = bool(body.get("dry_run", False))
            from main_brain import get_life_loop_daemon
            d = get_life_loop_daemon()
            out = d.run_consciousness_tick(dry_run=dry_run)
            return jsonify(out)
        except Exception as e:
            logger.warning(f"[brain] life/tick failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/consciousness', methods=['GET'])
    def brain_consciousness():
        """读取意识流状态（last_thought / mood / internal_dialogue / activities）。"""
        try:
            from main_brain.adapters.state import get_state_adapter
            return jsonify({"stream_of_consciousness": get_state_adapter().read_stream()})
        except Exception as e:
            logger.warning(f"[brain] consciousness read failed: {e}")
            return jsonify({"error": str(e)}), 500

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
                "activities_count": _get_activity_count(),
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

    @app.route('/brain/activities', methods=['GET'])
    def brain_activities():
        """列出所有已注册的活动定义（自省调试用）。

        从 activities/*.md frontmatter 发现的全部活动，含 metadata、
        allowed_tools、conditions。handler 状态：registered / fallback。
        """
        try:
            from main_brain.activities.registry import list_activities
            acts = list_activities()
            result = {}
            for name, act in sorted(acts.items()):
                result[name] = {
                    "description": act.description[:200],
                    "handler": act.handler_name,
                    "handler_ready": act.handler is not None,
                    "tick_types": act.tick_types,
                    "autonomy_min": act.autonomy_min,
                    "max_cycles": act.max_cycles,
                    "allowed_tools": list(act.allowed_tools),
                    "conditions": dict(act.conditions) if isinstance(act.conditions, dict) else {},
                }
            return jsonify({
                "count": len(result),
                "activities": result,
            })
        except Exception as e:
            logger.warning(f"[brain] activities failed: {e}")
            return jsonify({"error": str(e)}), 500

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

    @app.route('/brain/events/stream', methods=['GET'])
    def brain_events_stream():
        """SSE 实时事件流 — 订阅 EventBus 所有事件并推送到前端。"""
        import queue
        from core.event_bus import get_event_bus

        q = queue.Queue(maxsize=256)

        def handler(ev):
            try:
                q.put_nowait(json.dumps({
                    "source": ev.source,
                    "type": ev.type,
                    "data": ev.data,
                    "timestamp": ev.timestamp,
                }, ensure_ascii=False))
            except queue.Full:
                pass  # 客户端太慢，丢事件

        bus = get_event_bus()
        bus.on("*", "*", handler)

        def generate():
            try:
                # 发送初始连接确认
                yield f"event: connected\ndata: {json.dumps({'status': 'ok'})}\n\n"
                while True:
                    try:
                        payload = q.get(timeout=30)
                        yield f"event: brain_event\ndata: {payload}\n\n"
                    except queue.Empty:
                        # 30 秒无事件 → 发送心跳保持连接
                        yield ": heartbeat\n\n"
            except GeneratorExit:
                pass
            finally:
                bus.off("*", "*", handler)

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

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
            if window_size <= 0 or window_size > 10000:
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
            if window_size <= 0 or window_size > 10000:
                return jsonify({"error": "window_size 必须在 1..100"}), 400
            from main_brain.consolidation import preview_memory_consolidation
            return jsonify(preview_memory_consolidation(trigger, window_size=window_size))
        except Exception as e:
            logger.warning(f"[brain] memory/consolidate/preview failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/memory/consolidation/state', methods=['GET'])
    def brain_memory_consolidation_state():
        """沉淀检查点状态 + 预计下次整理时间。"""
        try:
            from main_brain.memory.consolidation import get_trace_store
            from main_brain.contracts import _now_iso
            from main_brain.clock import get_brain_clock
            from main_brain.config import get_brain_config
            from main_brain.adapters.output import get_output_adapter
            state = get_trace_store().get_state()
            now_iso = _now_iso()
            from datetime import datetime, timezone, timedelta
            next_at = ""

            if state.cooldown_until and state.cooldown_until > now_iso:
                next_at = state.cooldown_until
            else:
                try:
                    clock = get_brain_clock()
                    last_long = clock.get_last_run("long_tick")
                    interval = int(get_brain_config().get("long_tick_seconds", 3600))
                    if last_long:
                        last_dt = datetime.fromisoformat(last_long.replace("Z", "+00:00"))
                        next_dt = last_dt + timedelta(seconds=interval)
                        if next_dt > datetime.now(timezone.utc):
                            next_at = next_dt.isoformat()
                except Exception:
                    pass

            # 计算真正待处理条数：当前最大 seq - 上次处理的 seq 位置
            try:
                current_max = get_output_adapter().max_seq()
                pending_outputs = max(0, current_max - state.last_processed_seq)
            except Exception:
                pending_outputs = 0
            return jsonify({
                "last_processed_seq": state.last_processed_seq,
                "last_run_id": state.last_run_id,
                "last_saved_at": state.last_saved_at,
                "last_saved_memory_id": state.last_saved_memory_id,
                "policy_version": state.policy_version,
                "cooldown_until": state.cooldown_until,
                "pending_backlog": pending_outputs,
                "seen_hash_count": len(state.seen_hashes),
                "next_consolidation_at": next_at,
                "now": now_iso,
            })
        except Exception as e:
            logger.warning(f"[brain] memory/consolidation/state failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/memory/consolidation/recent', methods=['GET'])
    def brain_memory_consolidation_recent():
        """最近几次沉淀运行摘要（调试/回放）。query: limit。"""
        try:
            limit = int(request.args.get("limit", 10))
            from main_brain.memory.consolidation import get_trace_store
            return jsonify({"runs": get_trace_store().recent_runs(limit=limit)})
        except Exception as e:
            logger.warning(f"[brain] memory/consolidation/recent failed: {e}")
            return jsonify({"runs": [], "error": str(e)}), 500

    # ── procedural memory debug routes ────────────────────
    @app.route('/brain/procedural/mine', methods=['POST'])
    def brain_procedural_mine():
        try:
            body = request.get_json(silent=True) or {}
            window = int(body.get("window", 50))
            min_support = int(body.get("min_support", 3))
            min_success_rate = float(body.get("min_success_rate", 0.7))
            dry_run = bool(body.get("dry_run", False))
            if window <= 0 or window > 10000:
                return jsonify({"error": "window must be 1..10000"}), 400
            from main_brain.procedural_memory.scheduler import run_mining
            result = run_mining(window=window, min_support=min_support,
                                min_success_rate=min_success_rate, dry_run=dry_run)
            return jsonify(result)
        except Exception as e:
            logger.warning(f"[brain] procedural/mine failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/procedural/state', methods=['GET'])
    def brain_procedural_state():
        try:
            from main_brain.procedural_memory.scheduler import get_module_state
            return jsonify(get_module_state())
        except Exception as e:
            logger.warning(f"[brain] procedural/state failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/procedural/templates', methods=['GET'])
    def brain_procedural_templates():
        try:
            from main_brain.memory.procedural.store import get_procedure_store
            store = get_procedure_store()
            status = request.args.get("status")
            risk = request.args.get("risk")
            limit = int(request.args.get("limit", 50))
            templates = store.get_all_templates()
            if status:
                templates = [t for t in templates if t.status == status]
            if risk:
                templates = [t for t in templates if t.risk_level == risk]
            return jsonify({"count": len(templates), "templates": [t.to_dict() for t in templates[:limit]]})
        except Exception as e:
            logger.warning(f"[brain] procedural/templates failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/brain/procedural/match', methods=['POST'])
    def brain_procedural_match():
        try:
            body = request.get_json(silent=True) or {}
            context = body.get("context", {})
            top_k = int(body.get("top_k", 5))
            if not context:
                return jsonify({"error": "context required"}), 400
            from main_brain.procedural_memory.matcher import match_procedure_templates
            from main_brain.memory.procedural.store import get_procedure_store
            store = get_procedure_store()
            templates = store.get_templates_by_status("proposed", "active", "cooling")
            matches = match_procedure_templates(context, templates=templates, top_k=top_k)
            return jsonify({"ok": True, "matches": matches, "count": len(matches)})
        except Exception as e:
            logger.warning(f"[brain] procedural/match failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/procedural/feedback', methods=['POST'])
    def brain_procedural_feedback():
        try:
            body = request.get_json(silent=True) or {}
            template_id = body.get("template_id", "")
            run_id = body.get("run_id", "")
            result = body.get("result", "success")
            reward_delta = float(body.get("reward_delta", 0.2))
            notes = body.get("notes", "")
            if not template_id or not run_id:
                return jsonify({"error": "template_id and run_id required"}), 400
            from main_brain.procedural_memory.feedback import record_procedure_feedback
            res = record_procedure_feedback(template_id=template_id, run_id=run_id,
                                            result=result, reward_delta=reward_delta, notes=notes)
            return jsonify(res)
        except Exception as e:
            logger.warning(f"[brain] procedural/feedback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/procedural/promote', methods=['POST'])
    def brain_procedural_promote():
        try:
            body = request.get_json(silent=True) or {}
            template_id = body.get("template_id", "")
            if not template_id:
                return jsonify({"error": "template_id required"}), 400
            from main_brain.procedural_memory.feedback import promote_template
            return jsonify(promote_template(template_id))
        except Exception as e:
            logger.warning(f"[brain] procedural/promote failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/procedural/retire', methods=['POST'])
    def brain_procedural_retire():
        try:
            body = request.get_json(silent=True) or {}
            template_id = body.get("template_id", "")
            reason = body.get("reason", "")
            if not template_id:
                return jsonify({"error": "template_id required"}), 400
            from main_brain.procedural_memory.feedback import retire_template
            return jsonify(retire_template(template_id, reason=reason))
        except Exception as e:
            logger.warning(f"[brain] procedural/retire failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route('/brain/procedural/export-skill', methods=['POST'])
    def brain_procedural_export_skill():
        try:
            body = request.get_json(silent=True) or {}
            template_id = body.get("template_id", "")
            if not template_id:
                return jsonify({"error": "template_id required"}), 400
            from main_brain.procedural_memory.exporter import export_procedure_skill_draft
            return jsonify(export_procedure_skill_draft(template_id))
        except Exception as e:
            logger.warning(f"[brain] procedural/export-skill failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


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

