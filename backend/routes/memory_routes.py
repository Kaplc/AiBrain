"""Memory 模块 - 记忆 CRUD /memory"""
import logging
import threading
from flask import request, jsonify, Response, stream_with_context
from modules.brain.memory import (
    store_memory, search_memory, list_memories,
    delete_memory, update_memory, organize_memories,
    dedup_memories, refine_memories, apply_organize
)
from modules.brain.dedup import dedup_memories_iter, _dedup_pause_flag, _dedup_stop_flag

logger = logging.getLogger('memory')


def register(app, ready_state, logger, stats_db):
    @app.route('/memory/store', methods=['POST'])
    def store():
        data = request.get_json()
        text = (data or {}).get('text', '').strip()
        memory_meta = (data or {}).get('memory_meta')
        logger.info(f"[memory/store] text={text[:80]!r}, meta={memory_meta}")
        if not text:
            return jsonify({"error": "内容不能为空"})
        try:
            result = store_memory(text, memory_meta)
            logger.info(f"[memory/store] result={result}")
            stats_db.record_action(added=1)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/store] error: {e}")
            return jsonify({"error": str(e)})

    @app.route('/memory/search', methods=['POST'])
    def search():
        data = request.get_json()
        query = (data or {}).get('query', '').strip()
        ua = request.headers.get('User-Agent', '')
        is_mcp = 'python' in ua.lower() or 'urllib' in ua.lower()
        logger.info(f"[TRACE] /memory/search called | query={query[:80]!r} | remote={request.remote_addr} | is_mcp={is_mcp}")
        if not query:
            return jsonify({"results": []})
        try:
            results = search_memory(query)
            if not is_mcp:
                stats_db.add_search_history(query)
            return jsonify({"results": results})
        except Exception as e:
            return jsonify({"error": str(e), "results": []})

    @app.route('/memory/mcp/store', methods=['POST'])
    def mcp_store():
        data = request.get_json()
        text = (data or {}).get('text', '').strip()
        if not text:
            return jsonify({"error": "内容不能为空"})
        rowid = stats_db.append_stream('store', content=text, status='pending')

        def _bg_store():
            try:
                # MCP 保存的记忆标记 source: mcp
                result = store_memory(text, memory_meta={"source": "mcp"})
                stored_texts = result.get("stored_texts", [])
                if stored_texts:
                    new_content = "\n".join(f"• {t}" for t in stored_texts)
                    stats_db.update_stream_content(rowid, new_content)
                stats_db.record_action(added=1)
                stats_db.update_stream_status(rowid, 'done')
            except Exception as e:
                logger.error(f"[memory/mcp/store] 后台保存失败: {e}")
                stats_db.update_stream_status(rowid, 'error')

        threading.Thread(target=_bg_store, daemon=True).start()
        return jsonify({"rowid": rowid, "status": "pending"})

    @app.route('/memory/mcp/search', methods=['POST'])
    def mcp_search():
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

    @app.route('/memory/list', methods=['POST'])
    def list_route():
        data = request.get_json() or {}
        offset = data.get('offset', 0)
        limit = data.get('limit', 200)
        source = data.get('source')  # "user" or "mcp"
        logger.info(f"[memory/list] offset={offset} limit={limit} source={source}")
        try:
            memories = list_memories(offset=offset, limit=limit, source=source)
            logger.info(f"[memory/list] returned {len(memories)} memories")
            return jsonify({"memories": memories})
        except Exception as e:
            logger.error(f"[memory/list] error: {e}")
            return jsonify({"error": str(e), "memories": []})

    @app.route('/memory/delete', methods=['POST'])
    def delete():
        data = request.get_json() or {}
        memory_id = (data or {}).get('memory_id', '').strip()
        if not memory_id:
            return jsonify({"error": "缺少 memory_id"})
        try:
            result = delete_memory(memory_id)
            stats_db.record_action(deleted=1)
            stats_db.append_stream('delete', memory_id=memory_id)
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/memory/update', methods=['POST'])
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

    @app.route('/memory/update-async', methods=['POST'])
    def update_async():
        data = request.get_json() or {}
        memory_id = (data or {}).get('memory_id', '').strip()
        new_text = (data or {}).get('new_text', '').strip()
        if not memory_id or not new_text:
            return jsonify({"error": "缺少 memory_id 或 new_text"})
        def _do_update():
            try:
                update_memory(memory_id, new_text)
                stats_db.append_stream('update', content=new_text, memory_id=memory_id)
            except Exception:
                pass
        threading.Thread(target=_do_update, daemon=True).start()
        return jsonify({"result": "更新已提交后台"})

    @app.route('/memory/count', methods=['GET'])
    def memory_count():
        try:
            from modules.brain.memory import get_memory_count
            count = get_memory_count()
            return jsonify({"count": count})
        except Exception as e:
            logger.error(f"[memory/count] error: {e}")
            return jsonify({"count": 0, "error": str(e)})

    @app.route('/memory/search-history', methods=['GET'])
    def get_search_history():
        try:
            history = stats_db.get_search_history(limit=20)
            return jsonify({"history": history})
        except Exception as e:
            return jsonify({"error": str(e), "history": []})

    @app.route('/memory/search-history', methods=['DELETE'])
    def clear_search_history():
        try:
            stats_db.clear_search_history()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/memory/organize', methods=['POST'])
    def organize():
        data = request.get_json() or {}
        query = (data or {}).get('query', '').strip()
        if not query:
            return jsonify({"error": "查询词不能为空"})
        try:
            result = organize_memories(query)
            stats_db.append_stream('organize', content=f"dedup: {result.get('total_found', 0)} found")
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/memory/organize/dedup', methods=['POST'])
    def organize_dedup():
        data = request.get_json() or {}
        threshold = data.get('similarity_threshold', 0.85)
        try:
            result = dedup_memories(threshold)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/organize/dedup] 失败: {e}")
            return jsonify({"error": str(e), "groups": []})

    @app.route('/memory/organize/dedup/stream', methods=['POST'])
    def organize_dedup_stream():
        """SSE 流式去重分析，实时推送发现进度"""
        data = request.get_json() or {}
        threshold = data.get('similarity_threshold', 0.85)
        batch_size = data.get('batch_size', 30)

        # 重置停止/暂停标志
        _dedup_stop_flag.clear()
        _dedup_pause_flag.clear()

        def generate():
            import json
            try:
                for msg in dedup_memories_iter(threshold=threshold, batch_size=batch_size,
                                               pause_flag=_dedup_pause_flag, stop_flag=_dedup_stop_flag):
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"[dedup:stream] 生成器异常: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )

    @app.route('/memory/organize/dedup/pause', methods=['POST'])
    def organize_dedup_pause():
        """暂停去重分析（可恢复）"""
        _dedup_pause_flag.set()
        logger.info("[dedup:pause] 暂停去重分析")
        return jsonify({"ok": True, "paused": True})

    @app.route('/memory/organize/dedup/resume', methods=['POST'])
    def organize_dedup_resume():
        """恢复去重分析"""
        _dedup_pause_flag.clear()
        logger.info("[dedup:resume] 恢复去重分析")
        return jsonify({"ok": True, "resumed": True})

    @app.route('/memory/organize/dedup/stop', methods=['POST'])
    def organize_dedup_stop():
        """停止去重分析（不可恢复，重新开始）"""
        _dedup_stop_flag.set()
        _dedup_pause_flag.clear()
        logger.info("[dedup:stop] 停止去重分析")
        return jsonify({"ok": True, "stopped": True})

    @app.route('/memory/organize/refine', methods=['POST'])
    def organize_refine():
        data = request.get_json() or {}
        groups = data.get('groups', [])
        if not groups:
            return jsonify({"error": "没有需要精炼的分组", "refined": []})
        try:
            result = refine_memories(groups)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/organize/refine] 失败: {e}")
            return jsonify({"error": str(e), "refined": []})

    @app.route('/memory/organize/apply', methods=['POST'])
    def organize_apply():
        data = request.get_json() or {}
        items = data.get('items', [])
        if not items:
            return jsonify({"error": "没有需要写入的项目"})
        try:
            result = apply_organize(items)
            stats_db.append_stream('organize', content=f"apply: +{result['added']} -{result['deleted']}")
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/organize/apply] 失败: {e}")
            return jsonify({"error": str(e)})