"""
记忆核心逻辑 - 基于 mem0 + PipelineEngine 实现
mem0 全权管理：存储、去重、自动更新、自适应搜索。
MCP 只暴露 store + search，其余给前端 UI 用。
PipelineEngine 统一编排 store/search 的处理步骤。
"""
import json
import logging
import os
import threading

from modules.brain.mem0_adapter import get_mem0_client

logger = logging.getLogger('memory')

# 默认 user_id，mem0 需要至少一个 entity id
DEFAULT_USER_ID = "default"

# ── 记忆设置持久化路径：~/.aibrain/config/memory_settings.json ──
_SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), ".aibrain", "config", "memory_settings.json"
)

_DEFAULT_MEMORY_SETTINGS: dict = {
    "infer": True,
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
            if "infer" in data:
                result["infer"] = bool(data["infer"])
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
    if "infer" in data:
        _memory_settings["infer"] = bool(data["infer"])
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
    """预热记忆数量缓存（在 _preload 中调用）"""
    global _memory_count_cache
    try:
        client = get_mem0_client()
        result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=10000)
        _memory_count_cache = len(result.get("results", []))
        logger.info(f"[memory] 记忆数量缓存已预热: {_memory_count_cache} 条")
    except Exception as e:
        logger.warning(f"[memory] 预热记忆数量失败: {e}")
        _memory_count_cache = 0


def get_client():
    """兼容接口：返回 mem0 客户端"""
    return get_mem0_client()


def get_memory_count() -> int:
    """从 mem0 获取真实记忆数量"""
    global _memory_count_cache
    if _memory_count_cache is not None:
        return _memory_count_cache
    # 缓存未初始化时直接查询
    try:
        client = get_mem0_client()
        result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=10000)
        return len(result.get("results", []))
    except Exception:
        return 0


def _get_search_options():
    """根据数据量自适应返回最优搜索参数（使用缓存，避免每次 get_all）"""
    global _memory_count_cache
    if _memory_count_cache is None:
        # 缓存未预热时临时查询一次
        try:
            client = get_mem0_client()
            result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=10000)
            _memory_count_cache = len(result.get("results", []))
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
    use_infer = _memory_settings.get("infer", True)
    logger.info(f"[store_memory] START | text={text[:60]!r} | infer={use_infer}")

    # 创建 PipelineContext
    from .pipeline.context import PipelineContext
    ctx = PipelineContext(
        input_data=text,
        metadata={
            "infer": use_infer,
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
    client = get_mem0_client()

    use_infer = _memory_settings.get("infer", True)
    add_kwargs = {
        "user_id": "default",
        "infer": use_infer,
    }

    metadata = {"category": "user"}
    if memory_meta:
        metadata.update(memory_meta)
    add_kwargs["metadata"] = metadata

    try:
        result = client.add(text, **add_kwargs)
    except Exception as e:
        if use_infer:
            logger.warning(f"store_memory failed (infer=True): {e}, fallback infer=False")
            add_kwargs["infer"] = False
            result = client.add(text, **add_kwargs)
        else:
            raise

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
    if use_infer:
        try:
            from modules.brain.graph import get_graph
            graph = get_graph()
            if graph:
                for ev in events:
                    if ev.get("event") == "ADD" and ev.get("id"):
                        mem_text = ev.get("memory", "")
                        auto_entity_names = []
                        root_entity = '用户'
                        try:
                            from modules.brain.llm import extract_entities_llm
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

    if use_infer and events:
        try:
            def _bg_event_extract(events_list, original_text):
                from modules.brain.memory.events import get_event_store
                es = get_event_store()
                if not es:
                    return
                for ev in events_list:
                    if ev.get("event") == "ADD" and ev.get("id"):
                        try:
                            new_ids = es.extract_events_from_memory(ev["id"], ev.get("memory", ""))
                            if new_ids:
                                es.infer_event_chains(new_ids)
                        except Exception as e:
                            logger.warning(f"[store:event] failed for {ev['id'][:8]}: {e}")

            threading.Thread(target=_bg_event_extract, args=(events, text), daemon=True).start()
        except Exception as e:
            logger.warning(f"[store:event] async start failed (non-fatal): {e}")

    return {
        "result": msg,
        "stored_texts": stored_texts,
        "added_count": len(added),
        "deleted_count": len(deleted),
        "entities": list(dict.fromkeys(all_entity_names)),
    }


def search_memory(query: str) -> list[dict]:
    """搜索记忆，通过 PipelineEngine 编排各搜索阶段。

    Args:
        query: 搜索关键词

    Returns:
        list[dict]: [{id, text, score}, ...]
    """
    use_infer = _memory_settings.get("infer", True)
    logger.info(f"[search] START | query={query[:60]!r} | infer={use_infer}")

    # 创建 PipelineContext
    from .pipeline.context import PipelineContext
    ctx = PipelineContext(
        input_data=query,
        metadata={
            "infer": use_infer,
        },
    )

    # 尝试通过引擎执行
    if _try_pipeline_run("search", ctx):
        # 从 intermediate 中合并所有结果
        memories = list(ctx.intermediate.get("semantic_results", []))
        event_results = ctx.intermediate.get("event_results")
        if event_results:
            memories.extend(event_results)
        graph_results = ctx.intermediate.get("graph_results")
        if graph_results:
            memories.extend(graph_results)

        # 非 infer 模式下确保 entities 字段存在
        if not use_infer:
            for m in memories:
                m.setdefault("entities", [])

        logger.info(
            f"[search] DONE (pipeline) | 返回 {len(memories)} 条结果 | "
            f"sources={dict.fromkeys(m.get('source', 'unknown') for m in memories)}"
        )
        return memories

    # ── Fallback：引擎不可用时使用旧逻辑 ──
    logger.warning("[search] pipeline engine unavailable, using legacy path")
    return _search_memory_legacy(query)


def _search_memory_legacy(query: str) -> list[dict]:
    """旧版 search_memory 逻辑（引擎不可用时的 fallback）"""
    client = get_mem0_client()
    opts = _get_search_options()

    threshold = opts.get("threshold", 0.55)
    rerank = opts.get("rerank", False)
    MIN_COUNT = 15

    filters = {"user_id": DEFAULT_USER_ID}

    kwargs = {
        "query": query,
        "filters": filters,
        "top_k": 75,
        "threshold": threshold,
    }
    if rerank:
        kwargs["rerank"] = rerank

    result = client.search(**kwargs)
    memories = []
    for r in result.get("results", []):
        memories.append({
            "id": r.get("id"),
            "text": r["memory"],
            "score": round(r.get("score", 0), 4),
            "source": "semantic",
        })
    memories.sort(key=lambda x: x["score"], reverse=True)

    if len(memories) < MIN_COUNT:
        kwargs_no_thresh = {
            "query": query,
            "filters": filters,
            "top_k": MIN_COUNT,
        }
        if rerank:
            kwargs_no_thresh["rerank"] = rerank
        result2 = client.search(**kwargs_no_thresh)
        seen_ids = {m["id"] for m in memories}
        for r in result2.get("results", []):
            if r.get("id") not in seen_ids:
                memories.append({
                    "id": r.get("id"),
                    "text": r["memory"],
                    "score": round(r.get("score", 0), 4),
                    "source": "semantic",
                })
                seen_ids.add(r.get("id"))
        memories.sort(key=lambda x: x["score"], reverse=True)
        memories = memories[:MIN_COUNT]

    use_infer = _memory_settings.get("infer", True)

    # Phase 2: 事件反查
    if use_infer:
        try:
            from modules.brain.memory.events import get_event_store
            event_store = get_event_store()
            if event_store:
                matched_events = event_store.search_events_by_query(query, max_results=15)
                if matched_events:
                    chain_event_ids = set()
                    for ev in matched_events:
                        chain_event_ids.add(ev["id"])
                        for chain_ev in event_store.get_chain_for_event(ev["id"], max_depth=1):
                            chain_event_ids.add(chain_ev["id"])
                    chain_memory_ids = event_store.get_memories_for_events(list(chain_event_ids))
                    seen_ids = {m["id"] for m in memories}
                    new_mem_ids = [mid for mid in chain_memory_ids if mid not in seen_ids]
                    if new_mem_ids:
                        event_results = []
                        try:
                            from modules.brain.graph import get_graph
                            _g = get_graph()
                            if _g:
                                for mid in new_mem_ids[:10]:
                                    rows = _g._exec("SELECT mem0_id, text FROM memory_nodes WHERE mem0_id = ?", (mid,))
                                    if rows:
                                        event_results.append({
                                            "id": mid,
                                            "text": rows[0][1],
                                            "score": 0.5,
                                            "source": "event",
                                        })
                        except Exception:
                            pass
                        if event_results:
                            semantic_scores = [m["score"] for m in memories if m.get("source") == "semantic"]
                            base = min(semantic_scores) * 0.85 if semantic_scores else 0.5
                            for i, er in enumerate(event_results):
                                er["score"] = round(base - i * 0.001, 4)
                            memories.extend(event_results)
        except Exception as e:
            logger.warning(f"[search] Phase2 event recall failed (non-fatal): {e}")

    # Phase 3: 图增强
    if use_infer:
        try:
            from modules.brain.graph import get_graph
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
                    from modules.brain.llm import filter_related_memories
                    related_ids = filter_related_memories(query, candidates)
                    if related_ids:
                        related_map = {c["id"]: c for c in candidates}
                        semantic_scores = [m["score"] for m in memories if m.get("source") == "semantic"]
                        min_semantic = min(semantic_scores) if semantic_scores else 0.5
                        graph_base_score = min_semantic * 0.8
                        for i, rid in enumerate(related_ids[:10]):
                            c = related_map.get(rid)
                            if c:
                                c["score"] = round(graph_base_score - i * 0.001, 4)
                                c["source"] = "graph"
                                c["entities"] = entity_map.get(c["id"], [])
                                memories.append(c)
        except Exception as e:
            logger.warning(f"[graph] search enhancement failed (non-fatal): {e}")
    else:
        for m in memories:
            m["entities"] = []

    # Phase 4: 时间衰减
    if use_infer:
        try:
            from modules.brain.memory.events import get_event_store
            event_store = get_event_store()
            if event_store:
                all_mem_ids = [m["id"] for m in memories if m.get("id")]
                if all_mem_ids:
                    event_map = event_store.get_events_for_memories(all_mem_ids)
                    has_events = sum(1 for v in event_map.values() if v)
                    if has_events:
                        memories = event_store.apply_decay_to_results(memories, event_map)
        except Exception as e:
            logger.warning(f"[search] Phase4 time decay failed (non-fatal): {e}")

    logger.info(f"[search] DONE (legacy) | 返回 {len(memories)} 条结果")
    return memories


def list_memories(offset: int = 0, limit: int = 200, source: str = None) -> list[dict]:
    """列出记忆（前端 UI 用），按最新时间倒序排列

    Args:
        offset: 分页偏移
        limit: 每页数量限制（默认200）
        source: 可选过滤来源，如 "user"（用户保存）或 "mcp"（MCP工具保存）
    """
    client = get_mem0_client()
    filters = {"user_id": DEFAULT_USER_ID}
    if source:
        filters["metadata.source"] = source

    result = client.get_all(
        filters=filters,
        top_k=10000,
    )
    all_memories = result.get("results", [])
    all_memories.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    if source == "user":
        paged = all_memories[:20]
    else:
        paged = all_memories[offset:offset + limit]
    return [
        {
            "id": m["id"],
            "text": m["memory"],
            "timestamp": m.get("created_at"),
        }
        for m in paged
    ]


def delete_memory(memory_id: str) -> dict:
    """删除记忆（前端 UI 用），删前先取回文本内容"""
    client = get_mem0_client()
    memory_text = ''
    try:
        result = client.get(memory_id)
        if result:
            memory_text = result.get('memory', '') or result.get('text', '')
    except Exception as e:
        logger.warning(f"[delete_memory] get text failed for {memory_id}: {e}")
    client.delete(memory_id)

    try:
        from modules.brain.graph import get_graph
        graph = get_graph()
        if graph:
            graph.delete_memory(memory_id)
    except Exception as e:
        logger.warning(f"[graph] delete_memory failed (non-fatal): {e}")

    global _memory_count_cache
    if _memory_count_cache is not None:
        _memory_count_cache = max(0, _memory_count_cache - 1)
    return {"result": f"已删除记忆: {memory_id}", "text": memory_text}


def update_memory(memory_id: str, new_text: str) -> str:
    """更新记忆（前端 UI 用，用户手动编辑时调用）"""
    client = get_mem0_client()
    client.update(memory_id, new_text)
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
    use_infer = _memory_settings.get("infer", True)
    if not use_infer:
        return {
            "refined": [
                {
                    "group_id": group.get("group_id", 0),
                    "refined_text": "",
                    "category": "reference",
                    "refined": False,
                    "hint": "LLM模式已关闭，请手动编辑合并文本",
                }
                for group in groups
            ]
        }
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
