"""记忆 CRUD 路由：/store, /search, /list, /delete, /organize"""
from flask import request, jsonify

from modules.brain.memory import (
    store_memory, search_memory, list_memories,
    delete_memory, update_memory, organize_memories
)


def register(app, stats_db):
    @app.route('/store', methods=['POST'])
    def store():
        data = request.get_json()
        text = (data or {}).get('text', '').strip()
        hit_ids = (data or {}).get('hit_ids', [])
        if not text:
            return jsonify({"error": "内容不能为空"})
        # 检查当前已有记忆数量，20条以内允许 hit_ids 为空
        from modules.brain.memory import get_client
        from brain_mcp.config import settings as brain_settings
        client = get_client()
        total = client.count(collection_name=brain_settings.collection_name, exact=True).count
        if total >= 20 and not hit_ids:
            return jsonify({"error": "已有记忆达到20条，往后每次保存都需要引用已有记忆ID（hit_ids）"})
        try:
            result = store_memory(text, hit_ids=hit_ids or [])
            stats_db.record_action(added=1)
            stats_db.append_stream('store', content=text)
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
            results = search_memory(query)
            stats_db.append_stream('search', content=query)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e), "results": []})

    @app.route('/list', methods=['POST'])
    def list_route():
        data = request.get_json() or {}
        offset = data.get('offset', 0)
        limit = data.get('limit', 200)
        try:
            memories = list_memories(offset=offset, limit=limit)
            return jsonify({"memories": memories})
        except Exception as e:
            return jsonify({"error": str(e), "memories": []})

    @app.route('/delete', methods=['POST'])
    def delete():
        data = request.get_json() or {}
        memory_id = (data or {}).get('memory_id', '').strip()
        if not memory_id:
            return jsonify({"error": "缺少 memory_id"})
        try:
            # 先查内容再删除
            from modules.brain.memory import list_memories
            mems = list_memories()
            content = next((m['text'] for m in mems if m['id'] == memory_id), None)
            result = delete_memory(memory_id)
            stats_db.record_action(deleted=1)
            stats_db.append_stream('delete', memory_id=memory_id, content=content)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/update', methods=['POST'])
    def update():
        data = request.get_json() or {}
        memory_id = (data or {}).get('memory_id', '').strip()
        new_text = (data or {}).get('new_text', '').strip()
        if not memory_id:
            return jsonify({"error": "缺少 memory_id"})
        if not new_text:
            return jsonify({"error": "新内容不能为空"})
        try:
            result = update_memory(memory_id, new_text)
            stats_db.append_stream('update', content=new_text, memory_id=memory_id)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/organize', methods=['POST'])
    def organize():
        data = request.get_json() or {}
        query = (data or {}).get('query', '').strip()
        if not query:
            return jsonify({"error": "查询词不能为空"})
        try:
            result = organize_memories(query)
            stats_db.append_stream('organize', query=query, total=result.get('total_found', 0))
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)})
