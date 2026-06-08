"""
mem0 服务 API 路由

所有接口的请求/响应格式与 mem0 原始 SDK 保持一致，
主 Flask 的 Mem0HttpClient 透明调用这些接口。
"""
import logging


def register_routes(app, get_client, logger):
    """注册 mem0 API 路由到 Flask app"""

    @app.route('/memory/add', methods=['POST'])
    def memory_add():
        """存储记忆 — 替代 mem0.add()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True)
            text = data.get('text', '')
            if not text:
                return jsonify({"error": "text is required"}), 400

            kwargs = {}
            for key in ('user_id', 'infer', 'metadata', 'agent_id', 'run_id',
                        'app_id', 'session_id'):
                if key in data:
                    kwargs[key] = data[key]

            client = get_client()
            result = client.add(text, **kwargs)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/add] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/memory/search', methods=['POST'])
    def memory_search():
        """搜索记忆 — 替代 mem0.search()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True)
            query = data.get('query', '')
            if not query:
                return jsonify({"error": "query is required"}), 400

            kwargs = {}
            for key in ('user_id', 'filters', 'top_k', 'threshold', 'rerank',
                        'agent_id', 'run_id', 'app_id', 'session_id'):
                if key in data:
                    kwargs[key] = data[key]

            client = get_client()
            result = client.search(query, **kwargs)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/search] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/memory/list', methods=['POST'])
    def memory_list():
        """列出记忆 — 替代 mem0.get_all()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True) or {}

            kwargs = {}
            for key in ('user_id', 'agent_id', 'run_id', 'app_id', 'session_id',
                        'top_k', 'filters'):
                if key in data:
                    kwargs[key] = data[key]

            client = get_client()
            result = client.get_all(**kwargs)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/list] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/memory/get', methods=['POST'])
    def memory_get():
        """获取单条记忆 — 替代 mem0.get()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True)
            memory_id = data.get('id', '')
            if not memory_id:
                return jsonify({"error": "id is required"}), 400

            client = get_client()
            result = client.get(memory_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/get] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/memory/delete', methods=['POST'])
    def memory_delete():
        """删除记忆 — 替代 mem0.delete()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True)
            memory_id = data.get('id', '')
            if not memory_id:
                return jsonify({"error": "id is required"}), 400

            client = get_client()
            client.delete(memory_id)
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[memory/delete] error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/memory/update', methods=['POST'])
    def memory_update():
        """更新记忆 — 替代 mem0.update()"""
        from flask import request, jsonify
        try:
            data = request.get_json(force=True)
            memory_id = data.get('id', '')
            new_text = data.get('text', '')
            if not memory_id or not new_text:
                return jsonify({"error": "id and text are required"}), 400

            client = get_client()
            client.update(memory_id, new_text)
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[memory/update] error: {e}")
            return jsonify({"error": str(e)}), 500

    logger.info("mem0 API routes registered")
