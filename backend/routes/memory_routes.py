"""Memory 模块 - 记忆 CRUD /memory"""
import logging
import threading
from flask import request, jsonify, Response, stream_with_context
from modules.brain.memory import (
    store_memory, search_memory, list_memories,
    delete_memory, update_memory, organize_memories,
    dedup_memories, refine_memories, apply_organize,
    get_memory_settings, update_memory_settings,
)
from modules.brain.dedup import dedup_memories_iter, _dedup_pause_flag, _dedup_stop_flag

logger = logging.getLogger('memory')


def _search_all_categories(query: str) -> dict:
    """搜索所有记忆，按 score 排序取前15条，返回 results + stats"""
    try:
        results = search_memory(query)
        # 语义结果最多15条，图结果最多10条，合计25条
        semantic = [r for r in results if r.get('source') == 'semantic']
        graph = [r for r in results if r.get('source') == 'graph']
        semantic = sorted(semantic, key=lambda x: x['score'], reverse=True)[:15]
        graph = sorted(graph, key=lambda x: x['score'], reverse=True)[:10]
        sorted_results = semantic + graph
        return {
            "results": sorted_results,
            "stats": {
                "total": len(sorted_results),
                "semantic": len(semantic),
                "entity": len(graph),
            }
        }
    except Exception as e:
        logger.warning(f"search failed: {e}")
        return {"results": [], "stats": {"total": 0, "semantic": 0, "entity": 0}}


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
            stats_db.record_action(
                added=result.get('added_count', 0),
                deleted=result.get('deleted_count', 0),
            )
            entities = result.get('entities', [])
            stats_db.append_stream('store', content=text[:500], status='done', entities=','.join(entities))
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
            search_data = _search_all_categories(query)
            if not is_mcp:
                stats_db.add_search_history(query)
            return jsonify({"results": search_data["results"], "stats": search_data["stats"]})
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
                meta = {"source": "mcp"}
                result = store_memory(text, memory_meta=meta)
                stored = result.get("stored_texts", [])
                if stored:
                    new_content = "\n".join(f"• {t}" for t in stored)
                    stats_db.update_stream_content(rowid, new_content)
                # 写入关联实体到 stream
                entities = result.get("entities", [])
                if entities:
                    stats_db.update_stream_entities(rowid, ','.join(entities))
                stats_db.record_action(
                    added=result.get('added_count', 0),
                    deleted=result.get('deleted_count', 0),
                )
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
            return jsonify({"error": "搜索关键词不能为空"})
        rowid = stats_db.append_stream('search', content=query, status='pending')
        try:
            search_data = _search_all_categories(query)
            results = search_data["results"]
            stats = search_data["stats"]
            # 写入搜索统计到 stream entities 字段
            entities_str = f"语义搜索:{stats['semantic']},实体网络:{stats['entity']}"
            stats_db.update_stream_entities(rowid, entities_str)
            stats_db.update_stream_status(rowid, 'done')
            return jsonify({"results": results, "stats": stats})
        except Exception as e:
            stats_db.update_stream_status(rowid, 'error')
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
            stats_db.append_stream('delete', content=result.get('text', ''), memory_id=memory_id)
            return jsonify({"result": result.get('result', '已删除')})
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

    @app.route('/memory/settings', methods=['GET'])
    def memory_settings_get():
        """获取记忆运行时设置（如 infer 开关）"""
        return jsonify(get_memory_settings())

    @app.route('/memory/settings', methods=['POST'])
    def memory_settings_post():
        """更新记忆运行时设置（如 infer 开关）"""
        data = request.get_json() or {}
        result = update_memory_settings(data)
        return jsonify(result)

    @app.route('/memory/graph/entity', methods=['POST'])
    def graph_entity_search():
        """查询实体是否存在，返回关联记忆和关联实体"""
        data = request.get_json() or {}
        entity_name = data.get('entity_name', '').strip()
        if not entity_name:
            return jsonify({"error": "实体名称不能为空"})
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            result = graph.search_entity(entity_name)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/graph/entity] error: {e}")
            return jsonify({"error": str(e)})

    @app.route('/memory/graph/entities', methods=['POST'])
    def graph_list_entities():
        """列出所有实体及其关联记忆数量"""
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            entities = graph.list_entities()
            return jsonify({"entities": entities})
        except Exception as e:
            logger.error(f"[memory/graph/entities] error: {e}")
            return jsonify({"error": str(e)})

    @app.route('/memory/graph/visualization', methods=['POST'])
    def graph_visualization():
        """返回图谱可视化数据（节点+边）"""
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            data = graph.get_visualization_data()
            return jsonify(data)
        except Exception as e:
            logger.error(f"[memory/graph/visualization] error: {e}")
            return jsonify({"error": str(e), "nodes": [], "edges": []})

    @app.route('/memory/graph/link', methods=['POST'])
    def graph_link_entities():
        """在两个已有实体之间建立双向连接"""
        data = request.get_json() or {}
        entity_a = (data.get('entity_a', '')).strip()
        entity_b = (data.get('entity_b', '')).strip()
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            result = graph.link_entities(entity_a, entity_b)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/graph/link] error: {e}")
            return jsonify({"error": str(e)})
    @app.route('/memory/graph/merge', methods=['POST'])
    def graph_merge_entities():
        """合并两个实体，entity_b 的所有关联迁移到 entity_a"""
        data = request.get_json() or {}
        entity_a = (data.get('entity_a', '')).strip()
        entity_b = (data.get('entity_b', '')).strip()
        if not entity_a or not entity_b:
            return jsonify({"error": "entity_a 和 entity_b 都不能为空"})
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            graph.merge_entities(entity_a, entity_b)
            return jsonify({"success": True, "message": f"已将实体「{entity_b}」合并到「{entity_a}」"})
        except Exception as e:
            logger.error(f"[memory/graph/merge] error: {e}")
            return jsonify({"error": str(e)})

    @app.route('/memory/entity/stats', methods=['GET'])
    def entity_stats():
        """返回实体相关数据库统计和 NetworkX 内存图状态"""
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({
                    "entity_nodes": 0, "mentions": 0,
                    "memory_relations": 0, "typed_entity_relations": 0,
                    "graph_loaded": False, "graph_nodes": 0, "graph_edges": 0,
                })
            entity_nodes = graph._exec("SELECT COUNT(*) FROM entity_nodes")[0][0]
            mentions = graph._exec("SELECT COUNT(*) FROM mentions")[0][0]
            memory_relations = graph._exec("SELECT COUNT(*) FROM memory_relations")[0][0]
            typed_entity_relations = graph._exec("SELECT COUNT(*) FROM typed_entity_relations")[0][0]
            entity_relations = graph._exec("SELECT COUNT(*) FROM entity_relations")[0][0]
            g = graph._graph
            graph_loaded = g is not None
            graph_nodes = g.number_of_nodes() if graph_loaded else 0
            graph_edges = g.number_of_edges() if graph_loaded else 0
            return jsonify({
                "entity_nodes": entity_nodes,
                "mentions": mentions,
                "memory_relations": memory_relations,
                "typed_entity_relations": typed_entity_relations,
                "entity_relations": entity_relations,
                "graph_loaded": graph_loaded,
                "graph_nodes": graph_nodes,
                "graph_edges": graph_edges,
            })
        except Exception as e:
            logger.error(f"[memory/entity/stats] error: {e}")
            return jsonify({
                "entity_nodes": 0, "mentions": 0,
                "memory_relations": 0, "typed_entity_relations": 0,
                "entity_relations": 0,
                "graph_loaded": False, "graph_nodes": 0, "graph_edges": 0,
            })

    @app.route('/memory/graph/rebuild-entity-counts', methods=['POST'])
    def rebuild_entity_counts():
        """全量重建实体计数器（从 mentions 表聚合），用于初始化或修复统计"""
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if graph:
                graph.rebuild_entity_counts()
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "graph not available"})
        except Exception as e:
            logger.error(f"[memory/rebuild-entity-counts] error: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @app.route('/memory/entity/entitymgr', methods=['GET'])
    def entitymgr_list():
        """分页获取所有实体链接"""
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        search = request.args.get('search', '', type=str)
        offset = (page - 1) * page_size
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化", "links": [], "total": 0, "page": page, "page_size": page_size, "pages": 0})

            # 搜索条件
            if search:
                like_pattern = f'%{search}%'
                count_result = graph._exec(
                    "SELECT COUNT(*) FROM entity_relations WHERE from_entity LIKE ? OR to_entity LIKE ?",
                    (like_pattern, like_pattern)
                )
                total = count_result[0][0] if count_result else 0
                rows = graph._exec(
                    "SELECT from_entity, to_entity FROM entity_relations WHERE from_entity LIKE ? OR to_entity LIKE ? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (like_pattern, like_pattern, page_size, offset)
                )
            else:
                count_result = graph._exec("SELECT COUNT(*) FROM entity_relations")
                total = count_result[0][0] if count_result else 0
                rows = graph._exec(
                    "SELECT from_entity, to_entity FROM entity_relations ORDER BY rowid DESC LIMIT ? OFFSET ?",
                    (page_size, offset)
                )

            links = [{"entity_a": r[0], "entity_b": r[1]} for r in rows]
            pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            return jsonify({"links": links, "total": total, "page": page, "page_size": page_size, "pages": pages})
        except Exception as e:
            logger.error(f"[memory/entity/entitymgr] GET error: {e}")
            return jsonify({"error": str(e), "links": [], "total": 0, "page": page, "page_size": page_size, "pages": 0})

    @app.route('/memory/entity/entitymgr', methods=['POST'])
    def entitymgr_add():
        """添加实体链接，内部调用 graph.link_entities()"""
        data = request.get_json() or {}
        entity_a = (data.get('entity_a', '')).strip()
        entity_b = (data.get('entity_b', '')).strip()
        if not entity_a or not entity_b:
            return jsonify({"error": "entity_a 和 entity_b 都不能为空"})
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            result = graph.link_entities(entity_a, entity_b)
            return jsonify(result)
        except Exception as e:
            logger.error(f"[memory/entity/entitymgr] POST error: {e}")
            return jsonify({"error": str(e)})

    @app.route('/memory/entity/entitymgr', methods=['DELETE'])
    def entitymgr_delete():
        """删除两个实体之间的链接"""
        data = request.get_json() or {}
        entity_a = (data.get('entity_a', '')).strip()
        entity_b = (data.get('entity_b', '')).strip()
        if not entity_a or not entity_b:
            return jsonify({"error": "entity_a 和 entity_b 都不能为空"})
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if not graph:
                return jsonify({"error": "图数据库未初始化"})
            # 删除 (entity_a, entity_b) 和 (entity_b, entity_a) 两条记录
            graph._exec("DELETE FROM entity_relations WHERE entity_a = ? AND link_entity = ?", (entity_a, entity_b))
            graph._exec("DELETE FROM entity_relations WHERE entity_a = ? AND link_entity = ?", (entity_b, entity_a))
            # 同时从 typed_entity_relations 删除
            graph._exec("DELETE FROM typed_entity_relations WHERE entity_a = ? AND entity_b = ?", (entity_a, entity_b))
            graph._exec("DELETE FROM typed_entity_relations WHERE entity_a = ? AND entity_b = ?", (entity_b, entity_a))
            return jsonify({"success": True, "message": f"已删除实体「{entity_a}」与「{entity_b}」之间的链接"})
        except Exception as e:
            logger.error(f"[memory/entity/entitymgr] DELETE error: {e}")
            return jsonify({"error": str(e)})
