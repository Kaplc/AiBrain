"""Chat 路由 - /chat/*（SSE 流式 + 消息管理）"""
import json
import queue

from flask import request, jsonify, Response, stream_with_context


def register(app, ready_state, logger, stats_db):
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
        """SSE 流式发送消息"""
        user_msg = (request.get_json() or {}).get('message', '').strip()
        if not user_msg:
            return jsonify({'error': 'empty message'}), 400

        # 缺 API key → 503 + 引导到 Settings
        from core.settings import ConfigManager
        cfg = ConfigManager.get_instance().read_chat()
        if not cfg.get('chat_api_key'):
            return jsonify({
                'error': 'chat_api_key_missing',
                'message': '请先在 Settings → Chat 配置 API Key',
                'action': 'open_settings',
            }), 503

        # 写入用户消息
        stats_db.append_chat_message('user', user_msg, is_thought=0)

        # 获取 loop
        from modules.chat.agent_loop import get_consciousness_loop
        loop = get_consciousness_loop()
        if loop is None:
            return jsonify({'error': 'agent_not_running'}), 503

        q = queue.Queue(maxsize=64)
        status = loop.request_user_tick(user_msg, q)
        if status == 'busy':
            return jsonify({
                'error': 'agent_busy',
                'message': 'AI 正在思考上一条消息，请稍候再发',
            }), 409
        if status == 'rejected':
            return jsonify({'error': 'agent_not_running'}), 503

        def generate():
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"  # 心跳保活
                    continue
                t = evt.get('type')
                if t == 'token':
                    yield f"data: {json.dumps(evt)}\n\n"
                elif t == 'done':
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                elif t == 'error':
                    yield f"data: {json.dumps(evt)}\n\n"
                    # error 之后继续等 done（保证 partial 已落库）

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
        """清空对话消息（保留 idle 思绪）"""
        try:
            stats_db.clear_chat_messages()
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[chat] clear failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/chat/state', methods=['GET'])
    def chat_state():
        """获取意识流状态"""
        from modules.chat.agent_loop import get_consciousness_loop
        loop = get_consciousness_loop()
        if loop is None:
            return jsonify({
                'is_running': False,
                'idle_enabled': False,
                'idle_count': 0,
                'is_busy': False,
            })
        return jsonify(loop.get_state())
