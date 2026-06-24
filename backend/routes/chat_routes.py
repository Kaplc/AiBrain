"""Chat 路由 - /chat/*（SSE 流式 + 消息管理）"""
import json

from flask import request, jsonify, Response, stream_with_context


# ── 事件日志辅助 ──────────────────────────────────────────────
def _log_reply_event(text: str, source_event_id: str, trace_id: str = "") -> None:
    """将最终回复记录为一条 BrainEvent（补充事件链，挂到同一 trace 上）。"""
    try:
        from main_brain.contracts import BrainEvent, _new_event_id, _now_iso
        from main_brain.orchestrator import Orchestrator
        evt = BrainEvent(
            id=_new_event_id(),
            parent_id=source_event_id,
            trace_id=trace_id or source_event_id,
            source="chat",
            type="final_reply",
            modality="text",
            content=text[:500],
            timestamp=_now_iso(),
            salience=0.8,
        )
        Orchestrator.get_instance().process_event(evt, max_depth=1)
    except Exception:
        pass


def _write_chat_history(user_msg: str, reply_text: str) -> None:
    """把本轮对话写回对话历史和 work memory（同步 brain-first 与旧链路的行为）。"""
    if not reply_text:
        return
    # 1. 追加到 _conversation_history
    try:
        from modules.chat.loop import _conversation_history
        _conversation_history.append({"role": "user", "content": user_msg})
        _conversation_history.append({"role": "assistant", "content": reply_text})
    except Exception:
        pass
    # 2. 写入 output.json
    try:
        from modules.brain.memory.workmemory import get_work_memory
        get_work_memory().output_mem_write(reply_text, user_prompt=user_msg)
    except Exception:
        pass


# ── brain 状态辅助（外部刺激 + 反思） ──────────────────────────
def _get_drives_summary() -> dict:
    """获取驱动力全量值"""
    try:
        from modules.brain.state import get_drives
        return get_drives().get_all()
    except Exception:
        return {}


def _get_top_concerns(n: int = 5) -> list[dict]:
    """获取 top N 当前关注（node_id + effective 值）"""
    try:
        from modules.brain.state import get_concerns
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
            from modules.brain.memory.workmemory import get_work_memory
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

        # ── T002/T003: 大脑优先 SSE 流 ─────────────────────────
        # SSE start 立即返回（不等大脑处理）
        # 然后 generate() 内部尝试 brain-first → 有 final_reply 则直接输出 → 否则 fallback

        from modules.chat import ChatManager
        mgr = ChatManager.get_instance()

        # 标记用户活跃时间（不阻塞）
        try:
            from main_brain.adapters.state import get_state_adapter
            get_state_adapter().mark_user_contact()
        except Exception:
            pass

        def generate():
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            token_count = 0

            # 1. 尝试大脑主链路
            brain_reply = None
            brain_session_ok = False
            _brain_result = None
            try:
                from main_brain.config import get_brain_config as _get_bc
                from main_brain import get_brain_session
                if _get_bc().get_chat_mode() == _get_bc().CHAT_MODE_BRAIN_FIRST:
                    brain = get_brain_session().run_reactive(user_msg)
                    if _event_id:
                        brain["event_id"] = _event_id
                    _brain_result = brain
                    _strategy = brain.get("reply_strategy") or {}
                    _reply_text = ""
                    if isinstance(_strategy, dict):
                        _reply_text = _strategy.get("final_reply") or _strategy.get("text") or ""
                    if _reply_text:
                        brain_reply = _reply_text
                        brain_session_ok = True
                        logger.info(f"[chat] brain-first: run={brain.get('run_id')}")
                    else:
                        logger.info(f"[chat] brain-first: no final_reply, fallback with brain context")
            except Exception as e:
                logger.warning(f"[chat] brain-first failed (fallback): {e}")

            # 2. 大脑有回复 → 直接输出
            if brain_session_ok and brain_reply:
                yield f"data: {json.dumps({'type': 'token', 'content': brain_reply})}\n\n"
                token_count += 1
                _log_reply_event(brain_reply, _event_id or "", _event_trace_id or "")
                _write_chat_history(user_msg, brain_reply)
                logger.info(f"[chat] brain-first done: tokens={token_count}")
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # 3. Fallback：旧 ChatManager.send()（保留 brain 上下文注入 prompt）
            mgr.set_brain_context(_brain_result or {"fallback": True})
            _fallback_text = ""
            try:
                for event in mgr.send(user_msg):
                    t = event.get('type')
                    if t == 'token':
                        token_count += 1
                        _fallback_text += event.get('content', '')
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t in ('memory_step', 'tool_call', 'tool_history', 'token_estimate'):
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'usage':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'done':
                        logger.info(f"[chat] fallback done: tokens={token_count}")
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    elif t == 'error':
                        logger.error(f"[chat] fallback error: {event.get('message')}")
                        yield f"data: {json.dumps(event)}\n\n"
                        break
            except Exception as e:
                logger.error(f"[chat/send] fallback stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                if _fallback_text:
                    _log_reply_event(_fallback_text, _event_id or "", _event_trace_id or "")
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )

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
            from modules.brain.state import get_pending, get_concerns, get_drives
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
