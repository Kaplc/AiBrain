"""
记忆核心逻辑 - PipelineEngine 编排 store/search 的处理步骤。
"""
import json
import logging
import os
import threading

from modules.qdrant.store import get_qdrant_client, NEW_COLLECTION, LEGACY_COLLECTION

logger = logging.getLogger('memory')

# 默认 user_id
DEFAULT_USER_ID = "default"

# ── 记忆设置持久化路径：~/.aibrain/config/memory_settings.json ──
_SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), ".aibrain", "config", "memory_settings.json"
)

_DEFAULT_MEMORY_SETTINGS: dict = {
    "showGraphAnimation": True,
}


def _load_settings_from_disk() -> dict:
    """从磁盘读取记忆设置，文件不存在时返回默认值"""
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 只取已知字段，忽略未知键
            result = dict(_DEFAULT_MEMORY_SETTINGS)
            if "showGraphAnimation" in data:
                result["showGraphAnimation"] = bool(data["showGraphAnimation"])
            logger.info(f"[memory_settings] loaded from disk: {result}")
            return result
    except Exception as e:
        logger.warning(f"[memory_settings] failed to load from disk: {e}")
    return dict(_DEFAULT_MEMORY_SETTINGS)


def _save_settings_to_disk(settings: dict) -> None:
    """将记忆设置写入磁盘，目录不存在时自动创建"""
    try:
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        logger.info(f"[memory_settings] saved to disk: {_SETTINGS_PATH}")
    except Exception as e:
        logger.error(f"[memory_settings] failed to save to disk: {e}")


# ── 初始化：启动时从磁盘加载（无需重启即可持久化）────────────────
_memory_settings: dict = _load_settings_from_disk()


def get_memory_settings() -> dict:
    """返回当前记忆设置的副本"""
    return dict(_memory_settings)


def update_memory_settings(data: dict) -> dict:
    """更新记忆设置（仅覆盖已知字段），持久化到磁盘，返回更新后的设置"""
    if "showGraphAnimation" in data:
        _memory_settings["showGraphAnimation"] = bool(data["showGraphAnimation"])
    _save_settings_to_disk(_memory_settings)
    logger.info(f"[memory_settings] updated: {_memory_settings}")
    return get_memory_settings()

MEMORY_CATEGORY_MAP = {
    "life": {"id_type": "user_id",  "id_value": DEFAULT_USER_ID, "metadata": {"category": "life"}},
    "fact": {"id_type": "agent_id", "id_value": "fact",          "metadata": {"category": "fact"}},
    "exp":  {"id_type": "run_id",   "id_value": "exp",           "metadata": {"category": "exp"}},
}

# 记忆数量缓存：启动时预热，store 时自增，避免每次搜索都调 get_all
_memory_count_cache = None


def warmup_memory_count():
    """预热记忆数量缓存"""
    global _memory_count_cache
    try:
        from qdrant_client.http import models as q
        c = get_qdrant_client()
        cnt = c.count(collection_name=NEW_COLLECTION, exact=True).count
        cnt += c.count(collection_name=LEGACY_COLLECTION, exact=True).count
        _memory_count_cache = cnt
        logger.info(f"[memory] 记忆数量缓存已预热: {_memory_count_cache} 条")
    except Exception as e:
        logger.warning(f"[memory] 预热记忆数量失败: {e}")
        _memory_count_cache = 0


def get_client():
    """兼容接口：返回 Qdrant 客户端"""
    return get_qdrant_client()


def get_memory_count() -> int:
    """获取真实记忆数量"""
    global _memory_count_cache
    if _memory_count_cache is not None:
        return _memory_count_cache
    try:
        from qdrant_client.http import models as q
        c = get_qdrant_client()
        cnt = c.count(collection_name=NEW_COLLECTION, exact=True).count
        cnt += c.count(collection_name=LEGACY_COLLECTION, exact=True).count
        return cnt
    except Exception:
        return 0


def _get_search_options():
    """根据数据量自适应返回最优搜索参数（使用缓存，避免每次 get_all）"""
    global _memory_count_cache
    if _memory_count_cache is None:
        try:
            from qdrant_client.http import models as q
            c = get_qdrant_client()
            _memory_count_cache = c.count(collection_name=NEW_COLLECTION, exact=True).count
        except Exception:
            _memory_count_cache = 0
    total = _memory_count_cache

    if total < 100:
        return {"top_k": 50, "threshold": 0.55, "rerank": False}
    elif total <= 1000:
        return {"top_k": 50, "threshold": 0.55, "rerank": False}
    else:
        return {"top_k": 50, "threshold": 0.55, "rerank": True}


# ── PipelineEngine 兼容层 ──────────────────────────────────


def _record_store_stream(text: str, memory_meta: dict | None, entities: list):
    """Record store operation to stream table (all store paths unified)"""
    try:
        meta = memory_meta or {}
        if meta.get('_skip_core_stream'):
            return
        from core.database import StatsDB
        _path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'stats.db'
        )
        _sdb = StatsDB.get_instance(_path)
        if _sdb:
            _entities_str = ','.join(entities) if entities else ''
            _sdb.append_stream('store', content=text[:500], status='done', entities=_entities_str)
    except Exception as e:
        logger.debug(f"[store_memory] stream record skipped: {e}")


def _try_pipeline_run(pipeline_name: str, ctx):
    """尝试通过 PipelineEngine 执行，引擎未初始化时返回 False"""
    try:
        from .pipeline import get_engine
        engine = get_engine()
        if engine.get_pipeline(pipeline_name):
            engine.run(ctx, pipeline_name)
            return True
    except Exception as e:
        logger.warning(f"[pipeline] engine run failed for '{pipeline_name}': {e}, falling back to legacy")
    return False


def store_memory(text: str, memory_meta: dict = None) -> dict:
    """存储记忆，通过 PipelineEngine 编排各处理步骤。

    Args:
        text: 要存储的记忆文本
        memory_meta: 可选元数据，如 {"source": "user"} 或 {"source": "mcp"}

    Returns:
        dict: 包含 result 消息和实际存入的原始文本列表
            {"result": "已记住: 新增 N 条记忆", "stored_texts": [...]}
    """
    logger.info(f"[store_memory] START | text={text[:60]!r}")

    # 创建 PipelineContext
    from .pipeline.context import PipelineContext
    ctx = PipelineContext(
        input_data=text,
        metadata={
            "memory_meta": memory_meta,
        },
    )

    # 尝试通过引擎执行
    if _try_pipeline_run("store", ctx):
        # 从 context 中提取结果
        added = ctx.metadata.get("_added", [])
        updated = ctx.metadata.get("_updated", [])
        deleted = ctx.metadata.get("_deleted", [])

        parts = []
        if added:
            parts.append(f"新增 {len(added)} 条记忆")
        if updated:
            parts.append(f"更新 {len(updated)} 条记忆")
        if deleted:
            parts.append(f"自动清理 {len(deleted)} 条重复")

        stored_texts = added + updated
        msg = f"已记住: {', '.join(parts)}" if parts else "已处理"
        entities = ctx.intermediate.get("entities", [])

        logger.info(f"[store_memory] DONE (pipeline) | added={len(added)} deleted={len(deleted)}")
        # record stream for all store paths
        _record_store_stream(ctx.input_data, memory_meta, entities)
        return {
            "result": msg,
            "stored_texts": stored_texts,
            "added_count": len(added),
            "deleted_count": len(deleted),
            "entities": entities,
        }

    # ── Fallback：引擎不可用时使用旧逻辑 ──
    logger.warning("[store_memory] pipeline engine unavailable, using legacy path")
    return _store_memory_legacy(text, memory_meta)


def _store_memory_legacy(text: str, memory_meta: dict = None) -> dict:
    """旧版 store_memory 逻辑（引擎不可用时的 fallback）"""
    from .store import memory_store
    payload = {"category": "user"}
    if memory_meta:
        payload.update(memory_meta)
    result = memory_store(text, payload=payload)
    events = result.get("results", [])
    added = [e["memory"] for e in events if e.get("event") == "ADD"]
    updated = [e["memory"] for e in events if e.get("event") == "UPDATE"]
    deleted = [e["memory"] for e in events if e.get("event") == "DELETE"]

    global _memory_count_cache
    if _memory_count_cache is not None:
        _memory_count_cache += len(added) - len(deleted)
        _memory_count_cache = max(0, _memory_count_cache)

    parts = []
    if added:
        parts.append(f"新增 {len(added)} 条记忆")
    if updated:
        parts.append(f"更新 {len(updated)} 条记忆")
    if deleted:
        parts.append(f"自动清理 {len(deleted)} 条重复")

    stored_texts = added + updated
    msg = f"已记住: {', '.join(parts)}" if parts else "已处理"

    all_entity_names = []
    try:
        from main_brain.memory.graph import get_graph
        graph = get_graph()
        if graph:
            for ev in events:
                if ev.get("event") == "ADD" and ev.get("id"):
                    mem_text = ev.get("memory", "")
                    auto_entity_names = []
                    root_entity = '用户'
                    try:
                        from main_brain.memory.llm import extract_entities_llm
                        result = extract_entities_llm(mem_text)
                        auto_entity_names = result.get("entities", [])
                        root_entity = result.get("root", "用户")
                    except Exception:
                        pass
                    if not auto_entity_names:
                        continue
                    graph.link_memory(ev["id"], mem_text, link_entities=auto_entity_names, root_entity=root_entity)
                    all_entity_names.extend(auto_entity_names)
                    graph.increment_entity_counts(auto_entity_names)
    except Exception as e:
        logger.warning(f"[graph] link_memory failed (non-fatal): {e}")

    entities = list(dict.fromkeys(all_entity_names))
    # record stream for all store paths
    _record_store_stream(text, memory_meta, entities)
    return {
        "result": msg,
        "stored_texts": stored_texts,
        "added_count": len(added),
        "deleted_count": len(deleted),
        "entities": entities,
    }


def _boost_self_learn_memories(memories: list[dict], factor: float = 1.15) -> None:
    """提升自学习记忆的 score 并重新排序，使其更易出现在 top-k 结果中。"""
    for m in memories:
        payload = m.get("payload") or {}
        source = payload.get("source", "")
        if source == "self_learn":
            m["score"] = min(1.0, m.get("score", 0) * factor)
    memories.sort(key=lambda x: x.get("score", 0), reverse=True)


def search_memory(query: str) -> list[dict]:
    """搜索记忆，通过 PipelineEngine 编排各搜索阶段。

    建议使用完整的自然语言描述搜索（如"小明的生日是什么时候"），效果优于关键词拼接。

    Args:
        query: 自然语言搜索语句

    Returns:
        list[dict]: [{id, text, score, payload?}, ...]
    """
    logger.info(f"[search] START | query={query[:60]!r}")

    # 创建 PipelineContext
    from .pipeline.context import PipelineContext
    ctx = PipelineContext(
        input_data=query,
        metadata={},
    )

    # 尝试通过引擎执行
    if _try_pipeline_run("search", ctx):
        # 从 intermediate 中合并所有结果
        memories = list(ctx.intermediate.get("semantic_results", []))
        event_results = ctx.intermediate.get("event_results")
        if event_results:
            memories.extend(event_results)
        scene_results = ctx.intermediate.get("scene_results")
        if scene_results:
            memories.extend(scene_results)
        graph_results = ctx.intermediate.get("graph_results")
        if graph_results:
            memories.extend(graph_results)

        # 自学习记忆加权（内部已排序）
        _boost_self_learn_memories(memories)

        logger.info(
            f"[search] DONE (pipeline) | 返回 {len(memories)} 条结果 | "
            f"sources={dict.fromkeys(m.get('source', 'unknown') for m in memories)}"
        )
        return memories

    # ── Fallback：引擎不可用时使用旧逻辑 ──
    logger.warning("[search] pipeline engine unavailable, using legacy path")
    memories = _search_memory_legacy(query)
    _boost_self_learn_memories(memories)  # 内部已排序
    return memories


def _search_memory_legacy(query: str) -> list[dict]:
    """旧版 search_memory 逻辑（引擎不可用时的 fallback）"""
    from .store import memory_search
    opts = _get_search_options()
    threshold = opts.get("threshold", 0.55)
    MIN_COUNT = 15

    memories = memory_search(query, top_k=15, threshold=threshold)
    memories.sort(key=lambda x: x["score"], reverse=True)

    if len(memories) < MIN_COUNT:
        extra = memory_search(query, top_k=MIN_COUNT, threshold=0.0)
        seen_ids = {m["id"] for m in memories}
        for r in extra:
            if r.get("id") not in seen_ids:
                memories.append(r)
                seen_ids.add(r.get("id"))
        memories.sort(key=lambda x: x["score"], reverse=True)
        memories = memories[:MIN_COUNT]

    # Phase 3: 图增强
    try:
        from main_brain.memory.graph import get_graph
        graph = get_graph()
        if graph:
            mem_ids = [m["id"] for m in memories if m.get("id")]
            entity_map = graph.get_entities_for_memories(mem_ids)
            all_entities = []
            for m in memories:
                m["entities"] = entity_map.get(m["id"], [])
                all_entities.extend(m["entities"])
            all_entities = list(dict.fromkeys(all_entities))
            candidates = graph.search_related_new(mem_ids, all_entities, max_candidates=50)
            if candidates:
                related_map = {c["id"]: c for c in candidates}
                semantic_scores = [m["score"] for m in memories if m.get("source") == "semantic"]
                min_semantic = min(semantic_scores) if semantic_scores else 0.5
                graph_base_score = min_semantic * 0.8
                for i, c in enumerate(candidates[:10]):
                    c["score"] = round(graph_base_score - i * 0.001, 4)
                    c["source"] = "graph"
                    c["entities"] = entity_map.get(c["id"], [])
                    memories.append(c)
    except Exception as e:
        logger.warning(f"[graph] search enhancement failed (non-fatal): {e}")


    logger.info(f"[search] DONE (legacy) | 返回 {len(memories)} 条结果")
    return memories


def list_memories(offset: int = 0, limit: int = 200, source: str = None) -> list[dict]:
    """列出记忆（前端 UI 用），按最新时间倒序排列

    Args:
        offset: 分页偏移
        limit: 每页数量限制（默认200）
        source: 可选过滤来源，如 "user"（用户保存）或 "mcp"（MCP工具保存）
    """
    from qdrant_client.http import models as q
    c = get_qdrant_client()
    all_points, _ = c.scroll(
        collection_name=NEW_COLLECTION,
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )
    all_memories = []
    for p in all_points:
        pay = p.payload or {}
        all_memories.append({
            "id": str(p.id),
            "text": pay.get("display_text") or pay.get("text", ""),
            "timestamp": pay.get("created_at", ""),
        })
    all_memories.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    if source == "user":
        paged = all_memories[:20]
    else:
        paged = all_memories[offset:offset + limit]
    return paged


def delete_memory(memory_id: str) -> dict:
    """删除记忆（前端 UI 用）"""
    from qdrant_client.http import models as q
    c = get_qdrant_client()
    # 尝试从新集合删除
    try:
        c.delete(collection_name=NEW_COLLECTION, points_selector=q.PointIdsList(points=[memory_id]))
    except Exception:
        pass
    # 尝试从旧集合删除
    try:
        c.delete(collection_name=LEGACY_COLLECTION, points_selector=q.PointIdsList(points=[memory_id]))
    except Exception:
        pass
    try:
        from main_brain.memory.graph import get_graph
        graph = get_graph()
        if graph:
            graph.delete_memory(memory_id)
    except Exception as e:
        logger.warning(f"[graph] delete_memory failed (non-fatal): {e}")
    # 同步清理情景图索引，避免孤儿边
    try:
        from .scene_graph import get_scene_graph
        sg = get_scene_graph()
        if sg:
            sg.delete_scene(memory_id)
    except Exception as e:
        logger.warning(f"[scene_graph] delete_scene failed (non-fatal): {e}")
    global _memory_count_cache
    if _memory_count_cache is not None:
        _memory_count_cache = max(0, _memory_count_cache - 1)
    return {"result": f"已删除记忆: {memory_id}"}


def update_memory(memory_id: str, new_text: str) -> str:
    """更新记忆（前端 UI 用，用户手动编辑时调用）"""
    from modules.qdrant.store import get_qdrant_client, embed_texts, NEW_COLLECTION
    from qdrant_client.http import models as q
    c = get_qdrant_client()
    vector = embed_texts([new_text])[0]
    c.upsert(
        collection_name=NEW_COLLECTION,
        points=[q.PointStruct(id=memory_id, vector=vector, payload={"text": new_text, "updated_at": datetime.now(timezone.utc).isoformat()})],
        wait=True,
    )
    return f"已更新记忆: {new_text}"


def organize_memories(query: str) -> dict:
    """搜索相关记忆并整理（前端 UI 高级功能用）"""
    from .organizer import organize_memories as _organize

    related = search_memory(query)
    result = _organize(query, related)

    for mem_id in result["deleted_ids"]:
        delete_memory(mem_id)

    new_ids = []
    for mem in result.get("individual_memories", []):
        res = store_memory(mem["text"])
        new_ids.extend(res.get("stored_texts", []))

    result["new_memory_ids"] = new_ids
    result["new_memory_id"] = new_ids[0] if new_ids else None

    return result


def dedup_memories(threshold: float = 0.85) -> dict:
    """全量记忆去重分组（两步法第一步）"""
    from .dedup import dedup_memories as _dedup
    return _dedup(threshold)


def refine_memories(groups: list[dict]) -> dict:
    """LLM 精炼合并相似记忆组（两步法第二步）"""
    from .llm import refine_group

    refined = []
    for group in groups:
        result = refine_group(group["memories"])
        result["group_id"] = group.get("group_id", 0)
        refined.append(result)

    return {"refined": refined}


def apply_organize(items: list[dict]) -> dict:
    """用户确认后写入整理结果（删旧存新）"""
    applied = 0
    deleted = 0
    added = 0
    details = []

    for item in items:
        delete_ids = item.get("delete_ids", [])
        new_text = item.get("new_text", "").strip()

        if not new_text:
            continue

        for mem_id in delete_ids:
            try:
                delete_memory(mem_id)
                deleted += 1
            except Exception as e:
                logger.warning(f"[apply] 删除失败 {mem_id}: {e}")

        try:
            res = store_memory(new_text)
            added += 1
            new_id = res.get("stored_texts", [""])[0] if res.get("stored_texts") else ""
            details.append({"deleted_ids": delete_ids, "new_id": new_id, "new_text": new_text})
        except Exception as e:
            logger.warning(f"[apply] 存储失败: {e}")
            details.append({"deleted_ids": delete_ids, "new_id": "", "new_text": new_text, "error": str(e)})

        applied += 1

    return {"applied": applied, "deleted": deleted, "added": added, "details": details}
