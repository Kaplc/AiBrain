"""记忆 CRUD 路由：/store, /search, /list, /delete, /organize"""
from flask import request, jsonify


def register(app, stats_db):
    @app.route('/store', methods=['POST'])
    def store():
        data = request.get_json()
        text = (data or {}).get('text', '').strip()
        if not text:
            return jsonify({"error": "内容不能为空"})
        try:
            from brain_mcp._core import store_memory
            result = store_memory(text)
            stats_db.record_action(added=1)
            # 写入流
            mid = (result or {}).get('id', '') if isinstance(result, dict) else ''
            stats_db.append_stream('store', content=text, memory_id=mid)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/search', methods=['POST'])
    def search():
        data = request.get_json()
        query = (data or {}).get('query', '').strip()
        if not query:
            return jsonify({"results": []})
        try:
            from brain_mcp._core import search_memory
            results = search_memory(query)
            # 写入流
            stats_db.append_stream('search', content=query)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e), "results": []})

    @app.route('/list', methods=['POST'])
    def list_memories():
        data = request.get_json() or {}
        offset = data.get('offset', 0)
        limit = data.get('limit', 200)
        try:
            from brain_mcp._core import list_memories as _list
            memories = _list(offset=offset, limit=limit)
            return jsonify({"memories": memories})
        except Exception as e:
            return jsonify({"error": str(e), "memories": []})

    @app.route('/delete', methods=['POST'])
    def delete():
        data = request.get_json()
        memory_id = (data or {}).get('memory_id', '').strip()
        if not memory_id:
            return jsonify({"error": "缺少 memory_id"})
        try:
            from brain_mcp._core import delete_memory
            result = delete_memory(memory_id)
            stats_db.record_action(deleted=1)
            # 写入流
            stats_db.append_stream('delete', memory_id=memory_id)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/update', methods=['POST'])
    def update():
        data = request.get_json()
        memory_id = (data or {}).get('memory_id', '').strip()
        new_text = (data or {}).get('new_text', '').strip()
        if not memory_id:
            return jsonify({"error": "缺少 memory_id"})
        if not new_text:
            return jsonify({"error": "新内容不能为空"})
        try:
            from brain_mcp._core import update_memory
            result = update_memory(memory_id, new_text)
            stats_db.append_stream('update', content=new_text, memory_id=memory_id)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/organize', methods=['POST'])
    def organize():
        data = request.get_json()
        query = (data or {}).get('query', '').strip()
        if not query:
            return jsonify({"error": "查询词不能为空"})
        try:
            from brain_mcp._core import organize_memories
            result = organize_memories(query)
            stats_db.append_stream('organize', query=query, total=result.get('total_found', 0))
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)})
