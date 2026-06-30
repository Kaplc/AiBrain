"""Chat 路由 - /chat/*（SSE 流式 + 消息管理）"""
import json

from flask import request, jsonify





# ── brain 状态辅助（外部刺激 + 反思） ──────────────────────────
def _get_drives_summary() -> dict:
    """获取驱动力全量值"""
    try:
        from main_brain.state import get_drives
        return get_drives().get_all()
    except Exception:
        return {}


def _get_top_concerns(n: int = 5) -> list[dict]:
    """获取 top N 当前关注（node_id + effective 值）"""
    try:
        from main_brain.state import get_concerns
        top = get_concerns().all_effective(n)
        return [{"node_id": node_id, "effective": round(eff, 4)} for node_id, eff in top if eff > 0]
    except Exception:
        return []


def _get_reflection_summary() -> dict:
    """获取反思摘要（beliefs / interests / goals + 上次反思时间）"""
    try:
        from main_brain.narrative import get_self_narrative
        store = get_self_narrative()
        if store is None:
            return {}
        bio = store.get_autobiography()
        if not bio:
            return {}
        cs = bio.get("current_state", {})
        return {
            "last_reflection_at": cs.get("last_reflection_at"),
            "last_reflection_summary": cs.get("thinking", "")[:200],
            "beliefs": bio.get("beliefs", [])[:3],
            "interests": bio.get("interests", [])[:3],
            "goals": bio.get("goals", [])[:3],
            "open_questions": bio.get("open_questions", [])[:3],
        }
    except Exception:
        return {}


def register(app, ready_state, logger, stats_db):
    @app.route('/chat/history', methods=['GET'])
    def chat_history():
        """从 output.json 读取对话历史

        Returns:
            {"messages": [{role, content, time}, ...]}  user/assistant 交替
        """
        try:
            from main_brain.memory.workmemory import get_work_memory
            wm = get_work_memory()
            outputs = wm.output_mem_read()

            messages = []
            for entry in outputs:
                ts = entry.get("time", "")
                if entry.get("user"):
                    messages.append({
                        "role": "user",
                        "content": entry["user"],
                        "created_at": ts,
                    })
                if entry.get("assistant"):
                    messages.append({
                        "role": "assistant",
                        "content": entry["assistant"],
                        "created_at": ts,
                    })
            # 后台轮询调试日志
            last_msg = messages[-1]["content"][:40] if messages else "(无消息)"
            logger.info(f"[poll] /chat/history 返回 {len(messages)} 条消息 | 末条={last_msg!r}")
            return jsonify({"messages": messages})
        except Exception as e:
            logger.error(f"[chat] load history failed: {e}")
            return jsonify({"messages": [], "error": str(e)}), 500

    @app.route('/chat/messages', methods=['GET'])
    def chat_messages():
        """获取聊天历史（按时间 ASC）"""
        try:
            messages = stats_db.list_chat_messages(limit=500)
            return jsonify({"messages": messages})
        except Exception as e:
            logger.error(f"[chat] list messages failed: {e}")
            return jsonify({"messages": [], "error": str(e)}), 500

    @app.route('/chat/send', methods=['POST'])
    def chat_send():
        """SSE 流式发送消息（直接调 LLM，不经过后台线程）"""
        user_msg = (request.get_json() or {}).get('message', '').strip()
        if not user_msg:
            return jsonify({'error': 'empty message'}), 400

        # 缺 API key → 503
        from core.settings import ConfigManager
        cfg = ConfigManager.get_instance().read_llm()
        if not cfg.get('api_key'):
            logger.warning(f"[chat] send failed: API key missing (base_url={cfg.get('base_url','')!r})")
            return jsonify({
                'error': 'api_key_missing',
                'message': '请先在 Settings → LLM 配置 API Key',
                'action': 'open_settings',
            }), 503

        # T003 / T009: 用户消息入脑（fallback 开关控制）
        _event_id = None
        _event_trace_id = None
        try:
            from main_brain.config import EVENT_ORCHESTRATOR_ENABLED as _EVT_ENABLED
            if _EVT_ENABLED:
                from main_brain.contracts import make_chat_event
                from main_brain.orchestrator import Orchestrator
                event = make_chat_event(user_msg)
                _event_id = event.id
                _event_trace_id = event.trace_id
                Orchestrator.get_instance().process_event(event)
                from modules.chat import ChatManager as _CM
                _CM.get_instance().set_event_trace(event.trace_id, event.id)
                logger.info(f"[chat] event created: id={event.id} trace={event.trace_id}")
            else:
                logger.debug("[chat] event_orchestrator disabled, skip event creation")
        except Exception as e:
            logger.warning(f"[chat] event creation skipped (non-fatal): {e}")

        # ── 写 user 条目（立即落盘 + emit 推前端实时刷新），再入队意识流处理 ──
        # 回复由意识流 speak 写独立 assistant 条目，前端经 EventSource 自动刷新拿到
        try:
            from main_brain.memory.workmemory import get_work_memory
            get_work_memory().output_mem_write(content="", user_prompt=user_msg)
            logger.info(f"[chat] user msg stored: {user_msg[:40]}")
        except Exception as e:
            logger.warning(f"[chat] store user msg failed: {e}")

        try:
            from main_brain import get_brain_session
            get_brain_session().run_reactive(user_msg)
            logger.info(f"[chat] queued for consciousness: msg={user_msg[:40]}")
        except Exception as e:
            logger.warning(f"[chat] queue failed: {e}")

        # 标记用户活跃时间
        try:
            from main_brain.adapters.state import get_state_adapter
            get_state_adapter().mark_user_contact()
        except Exception:
            pass

        return jsonify({'ok': True, 'queued': True})

    @app.route('/chat/clear', methods=['POST'])
    def chat_clear():
        """清空对话消息"""
        try:
            stats_db.clear_chat_messages()
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[chat] clear failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/chat/state', methods=['GET'])
    def chat_state():
        """获取意识流状态 + brain 摘要"""
        from modules.chat import ChatManager
        mgr = ChatManager.get_instance()
        state = mgr.get_loop_state()
        # brain 摘要（plan T018）：失败不影响主状态
        try:
            from main_brain.adapters.state import get_state_adapter
            from main_brain.logging.event_log import get_event_log
            from main_brain import get_life_loop_daemon
            life = get_state_adapter().read_life_state()
            elog = get_event_log()
            # idle_seconds 已由 read_life_state() 实时注入（compute_idle_seconds）
            state["brain"] = {
                "last_reactive_run_id": elog.last_run_id("reactive"),
                "last_background_run_id": elog.last_run_id("background"),
                "life_loop_status": life.get("life_loop_status", ""),
                "current_focus": life.get("current_focus", ""),
                "current_activity": life.get("current_activity", ""),
                "idle_seconds": life.get("idle_seconds", 0),
                "energy": life.get("energy", 0.6),
                "mood": life.get("mood", {}),
                "open_loop_count": len(life.get("open_loops", []) or []),
                "pending_expression_count": len(life.get("pending_expressions", []) or []),
                "last_error": life.get("last_error", ""),
                "scheduler_running": get_life_loop_daemon().is_running(),
                # 外部刺激：驱动力 + 当前关注
                "drives": _get_drives_summary(),
                "top_concerns": _get_top_concerns(5),
                # 反思摘要
                "reflection": _get_reflection_summary(),
            }
        except Exception as e:
            logger.warning(f"[chat] brain state enrich failed: {e}")
            state["brain"] = {"error": str(e)}
        return jsonify(state)

    @app.route('/chat/proactive', methods=['POST'])
    def trigger_proactive():
        """手动触发猫猫主动消息：生成 + 写 output.json 给用户（强制发送，不受冷却限制）"""
        try:
            from main_brain.state import get_pending, get_concerns, get_drives
            p = get_pending()
            # 先生成 pending
            p.evaluate_and_generate()
            # 手动触发：强制发送，绕过 1h 冷却和 refractory
            content = p.proactive_send(force=True)
            # 如果没有未表达 pending，从最高 concern 临时建一个再发
            if content is None:
                top = get_concerns().all_effective(1)
                if top:
                    node_id, eff = top[0]
                    drive = get_drives().drive_for_node(node_id)
                    score = round(eff * drive, 4)
                    p._create("recent_interest", node_id, score, source="concern")
                    content = p.proactive_send(force=True)
            if content is None:
                return jsonify({"sent": False, "content": None, "reason": "nothing to say"})
            # 立即刷入 output.json
            flushed = p.flush_proactive_buffer()
            return jsonify({"sent": flushed > 0, "content": content})
        except Exception as e:
            logger.warning(f"[chat] proactive trigger failed: {e}")
            return jsonify({"sent": False, "error": str(e)})
