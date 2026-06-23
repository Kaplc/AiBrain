"""
情景图扩散 API 路由 — /memory/scene/*

提供情景图检索、扩散路径解释、索引重建与图规模观测。
（旧记忆迁移相关路由按需跳过：/migrate、/migration/status。）

路由清单（对应 plan API 设计章节）：
  POST /memory/scene/search        按情景图扩散检索
  POST /memory/scene/explain       返回某次召回的扩散路径(trace)
  POST /memory/scene/reindex       重建情景图索引（后台执行）
  GET  /memory/scene/graph/stats   图规模与边数 + reindex 进度
  GET  /memory/scene/anchor/<name> 查询某锚点关联的情景
  GET  /memory/scene/<scene_id>    查询单条情景详情
"""
import logging
import threading
from flask import request

logger = logging.getLogger('scene')

# 后台 reindex 状态（模块级，简单进程内追踪）
_reindex_lock = threading.Lock()
_reindex_state = {"running": False, "total": 0, "linked": 0, "done": False, "error": None}


def _is_ready(ready_state) -> bool:
    """ready_state 是 dict {model, qdrant, device}，两者皆 True 才算就绪"""
    return bool(ready_state.get("model")) and bool(ready_state.get("qdrant"))


def register(app, ready_state, _logger, stats_db):

    @app.route('/memory/scene/search', methods=['POST'])
    def scene_search():
        """按情景图扩散检索

        请求: {"query": "...", "top_k": 20, "mode": "default"}
        响应: {"ok": true, "results": [{id,text,score,source,trace:{seed_nodes,hop,relation_type}}]}
        """
        if not _is_ready(ready_state):
            return {"error": "系统尚未就绪"}, 503
        data = request.get_json(silent=True) or {}
        query = (data.get('query') or '').strip()
        try:
            top_k = int(data.get('top_k', 20))
        except (TypeError, ValueError):
            top_k = 20
        if not query:
            return {"ok": False, "error": "query 不能为空"}, 400
        try:
            from modules.brain.memory.store import memory_search
            from modules.brain.memory.scene_diffusion import get_scene_diffusion
            sem = memory_search(query, top_k=15, threshold=0.55)
            diff = get_scene_diffusion()
            if not diff or not diff.available():
                return {"ok": True, "results": [], "note": "scene graph unavailable"}
            results = diff.search(query, sem, top_k=top_k, with_trace=True)
            return {"ok": True, "results": results}
        except Exception as e:
            logger.warning(f"[scene/search] error: {e}")
            return {"ok": False, "error": str(e)}, 500

    @app.route('/memory/scene/explain', methods=['POST'])
    def scene_explain():
        """返回扩散召回的 trace 路径（FR-008 可解释）

        请求: {"query": "...", "result_ids": ["id1", ...]}  # result_ids 可选
        """
        if not _is_ready(ready_state):
            return {"error": "系统尚未就绪"}, 503
        data = request.get_json(silent=True) or {}
        query = (data.get('query') or '').strip()
        result_ids = data.get('result_ids')
        if not query:
            return {"ok": False, "error": "query 不能为空"}, 400
        try:
            from modules.brain.memory.store import memory_search
            from modules.brain.memory.scene_diffusion import get_scene_diffusion
            sem = memory_search(query, top_k=15, threshold=0.55)
            diff = get_scene_diffusion()
            if not diff or not diff.available():
                return {"ok": True, "traces": [], "note": "scene graph unavailable"}
            return {"ok": True, **diff.explain(query, sem, result_ids)}
        except Exception as e:
            logger.warning(f"[scene/explain] error: {e}")
            return {"ok": False, "error": str(e)}, 500

    @app.route('/memory/scene/reindex', methods=['POST'])
    def scene_reindex():
        """重建情景图索引（从 Qdrant payload 全量重建，后台分批执行）

        幂等：清空三表后按 payload 重建。迁移回放/索引恢复用。
        """
        if not _is_ready(ready_state):
            return {"error": "系统尚未就绪"}, 503
        with _reindex_lock:
            if _reindex_state["running"]:
                return {"ok": False, "error": "reindex 正在进行中"}, 409
            _reindex_state.update(
                {"running": True, "total": 0, "linked": 0, "done": False, "error": None}
            )
        threading.Thread(target=_run_reindex, daemon=True).start()
        return {"ok": True, "note": "reindex 已在后台启动，GET /memory/scene/graph/stats 查看进度"}

    @app.route('/memory/scene/graph/stats', methods=['GET'])
    def scene_graph_stats():
        """图规模与边数 + reindex 进度（FR-012 运行观测）"""
        try:
            from modules.brain.memory.scene_graph import get_scene_graph
            sg = get_scene_graph()
            stats = sg.get_stats() if sg else {}
            with _reindex_lock:
                stats["reindex"] = {k: _reindex_state[k] for k in
                                    ("running", "total", "linked", "done", "error")}
            return {"ok": True, "stats": stats}
        except Exception as e:
            logger.warning(f"[scene/graph/stats] error: {e}")
            return {"ok": False, "error": str(e)}, 500

    @app.route('/memory/scene/anchor/<path:name>', methods=['GET'])
    def scene_anchor(name):
        """查询某锚点关联的情景列表"""
        try:
            from modules.brain.memory.scene_graph import get_scene_graph
            sg = get_scene_graph()
            if not sg:
                return {"ok": False, "error": "scene graph 未初始化"}, 503
            anchor = sg.find_anchor(name)
            if not anchor:
                return {"ok": False, "error": f"锚点 '{name}' 不存在"}, 404
            scene_ids = sg.get_scenes_for_anchor(name, limit=50)
            texts = _fetch_scene_texts(scene_ids)
            scenes = [{"id": sid, "text": texts.get(sid, "")} for sid in scene_ids]
            return {"ok": True, "anchor": anchor, "scenes": scenes}
        except Exception as e:
            logger.warning(f"[scene/anchor] error: {e}")
            return {"ok": False, "error": str(e)}, 500

    @app.route('/memory/scene/<path:scene_id>', methods=['GET'])
    def scene_detail(scene_id):
        """查询单条情景详情（Qdrant payload + 图锚点）"""
        try:
            from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
            from modules.brain.memory.scene_graph import get_scene_graph
            client = get_qdrant_client()
            points = client.retrieve(
                collection_name=NEW_COLLECTION, ids=[scene_id],
                with_payload=True, with_vectors=False,
            )
            if not points:
                return {"ok": False, "error": f"scene '{scene_id}' 不存在"}, 404
            payload = points[0].payload or {}
            sg = get_scene_graph()
            anchors = sg.get_scene_anchors(scene_id) if sg else []
            return {"ok": True, "scene": {"id": str(points[0].id), "payload": payload, "anchors": anchors}}
        except Exception as e:
            logger.warning(f"[scene/detail] error: {e}")
            return {"ok": False, "error": str(e)}, 500


# ── 后台 reindex ────────────────────────────────────────────


def _run_reindex():
    """后台执行 reindex，更新模块级状态"""
    try:
        from modules.brain.memory.scene_graph import get_scene_graph
        sg = get_scene_graph()
        if not sg:
            raise RuntimeError("scene graph 未初始化")

        def _progress(n):
            with _reindex_lock:
                _reindex_state["total"] = n

        result = sg.reindex(batch_callback=_progress)
        sg.rebuild_anchor_counts()
        with _reindex_lock:
            _reindex_state["running"] = False
            _reindex_state["linked"] = result.get("linked", 0)
            _reindex_state["total"] = result.get("total", _reindex_state["total"])
            _reindex_state["done"] = True
        logger.info(f"[scene/reindex] DONE | {result}")
    except Exception as e:
        with _reindex_lock:
            _reindex_state["running"] = False
            _reindex_state["error"] = str(e)
            _reindex_state["done"] = True
        logger.warning(f"[scene/reindex] failed: {e}")


def _fetch_scene_texts(scene_ids: list[str]) -> dict:
    """批量取 scene 的展示文本"""
    if not scene_ids:
        return {}
    try:
        from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
        client = get_qdrant_client()
        points = client.retrieve(
            collection_name=NEW_COLLECTION, ids=scene_ids,
            with_payload=True, with_vectors=False,
        )
        out = {}
        for p in points:
            pay = p.payload or {}
            out[str(p.id)] = pay.get("display_text") or pay.get("text", "")
        return out
    except Exception as e:
        logger.warning(f"[scene] fetch texts failed: {e}")
        return {}
