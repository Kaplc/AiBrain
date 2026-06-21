"""Chat 路由 - /chat/*（SSE 流式 + 消息管理）"""
import json

from flask import request, jsonify, Response, stream_with_context


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

        # 获取 ChatManager 并发送
        from modules.chat import ChatManager
        mgr = ChatManager.get_instance()
        logger.info(f"[chat] send start: msg={user_msg[:60]!r}")

        # Reactive BrainSession：回复前先内部思考几轮（可配置开关，失败自动回退）
        try:
            from main_brain.config import get_brain_config
            if get_brain_config().session_enabled:
                from main_brain import get_brain_session
                brain = get_brain_session().run_reactive(user_msg)
                mgr.set_brain_context(brain)
                logger.info(
                    f"[chat] brain_session done: run={brain.get('run_id')} "
                    f"cycles={brain.get('cycle_count')} stop={brain.get('stop_reason')}"
                )
            else:
                mgr.set_brain_context({})
        except Exception as e:
            logger.warning(f"[chat] brain_session skipped (fallback to plain send): {e}")
            mgr.set_brain_context({})

        def generate():
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            token_count = 0
            try:
                for event in mgr.send(user_msg):
                    t = event.get('type')
                    if t == 'token':
                        token_count += 1
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'memory_step':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'tool_call':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'tool_history':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'token_estimate':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'usage':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'done':
                        logger.info(f"[chat] send done: tokens={token_count}")
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    elif t == 'error':
                        logger.error(f"[chat] send error: {event.get('message')}")
                        yield f"data: {json.dumps(event)}\n\n"
                        break
            except Exception as e:
                logger.error(f"[chat/send] stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
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
                "open_loop_count": len(life.get("open_loops", []) or []),
                "pending_expression_count": len(life.get("pending_expressions", []) or []),
                "last_error": life.get("last_error", ""),
                "scheduler_running": get_life_loop_daemon().is_running(),
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
