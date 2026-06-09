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
        cfg = ConfigManager.get_instance().read_chat()
        if not cfg.get('chat_api_key'):
            logger.warning(f"[chat] send failed: API key missing (base_url={cfg.get('chat_base_url','')!r})")
            return jsonify({
                'error': 'chat_api_key_missing',
                'message': '请先在 Settings → Chat 配置 API Key',
                'action': 'open_settings',
            }), 503

        # 获取 ChatManager 并发送
        from modules.chat import ChatManager
        mgr = ChatManager.get_instance()
        logger.info(f"[chat] send start: msg={user_msg[:60]!r}")

        def generate():
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            token_count = 0
            try:
                for event in mgr.send(user_msg):
                    t = event.get('type')
                    if t == 'token':
                        token_count += 1
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'tool_call':
                        yield f"data: {json.dumps(event)}\n\n"
                    elif t == 'tool_history':
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
        """获取意识流状态"""
        from modules.chat import ChatManager
        mgr = ChatManager.get_instance()
        return jsonify(mgr.get_loop_state())
