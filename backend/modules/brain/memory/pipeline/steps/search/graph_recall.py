"""
GraphRecall Step - 共现召回 + LLM 过滤
通过实体网络召回额外相关记忆

读取 ctx.intermediate:
  - semantic_results: 语义搜索结果
  - event_results: 事件召回结果（可选）

写入 ctx.intermediate:
  - graph_results: 共现召回的额外记忆列表
"""
import logging

logger = logging.getLogger('memory.pipeline')


def _set_status(s: str):
    try:
        from modules.chat import ChatManager
        ChatManager.get_instance().set_status(s)
    except Exception:
        pass


def execute(ctx) -> None:
    _set_status("实体搜索")
    """执行 GraphRecall 步骤：实体映射 + 共现召回 + LLM 过滤

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:graph_recall] infer=false, skip")
        for m in ctx.intermediate.get("semantic_results", []):
            m.setdefault("entities", [])
        return
    if meta.get("_info_enough"):
        logger.info("[step:graph_recall] info_enough=true, skip")
        for m in ctx.intermediate.get("semantic_results", []):
            m.setdefault("entities", [])
        return

    query = ctx.input_data
    semantic_results = ctx.intermediate.get("semantic_results")
    if semantic_results is None:
        logger.info("[step:graph_recall] no semantic_results, skip")
        return

    from modules.brain.graph import get_graph
    graph = get_graph()
    if not graph:
        logger.warning("[step:graph_recall] graph not available, skip")
        for m in semantic_results:
            m.setdefault("entities", [])
        return

    # 合并所有已有结果用于实体映射
    all_memories = list(semantic_results)
    event_results = ctx.intermediate.get("event_results")
    if event_results:
        all_memories.extend(event_results)

    mem_ids = [m["id"] for m in all_memories if m.get("id")]
    logger.info(f"[step:graph_recall] 向量命中 {len(mem_ids)} 条 | query={query[:50]!r}")

    # 附上每条记忆的关联实体
    entity_map = graph.get_entities_for_memories(mem_ids)
    all_entities = []
    for m in all_memories:
        m["entities"] = entity_map.get(m["id"], [])
        all_entities.extend(m["entities"])
    all_entities = list(dict.fromkeys(all_entities))
    logger.info(f"[step:graph_recall] 实体映射完成 | {len(entity_map)} 条有实体关联 | 总实体={len(all_entities)}")

    # mentions 共现召回
    candidates = graph.search_related_new(mem_ids, all_entities, max_candidates=50)
    if not candidates:
        logger.info("[step:graph_recall] 共现召回无候选记忆")
        return

    logger.info(f"[step:graph_recall] 共现召回 {len(candidates)} 条候选记忆 | 调用 LLM 过滤")
    for i, c in enumerate(candidates):
        logger.info(f"[step:graph_recall] 候选[{i}] co_count={c.get('co_count',0)} | {c['id'][:8]} | {c['text'][:80]}")

    # LLM 批量过滤（使用 MemoryRelationAgent）
    try:
        from modules.LLM import get_agent_manager
        agent = get_agent_manager().get("memory_relation")
        related_ids = agent.run({"query": query, "candidates": candidates})
    except Exception as e:
        logger.warning(f"[step:graph_recall] MemoryRelationAgent failed, using raw candidates: {e}")
        related_ids = [c["id"] for c in candidates[:10]]

    if not related_ids:
        logger.info("[step:graph_recall] LLM 过滤后无相关记忆")
        return

    related_map = {c["id"]: c for c in candidates}
    min_semantic = ctx.intermediate.get("min_semantic_score", 0.5)
    graph_base_score = min_semantic * 0.8
    added = []
    for i, rid in enumerate(related_ids[:10]):
        c = related_map.get(rid)
        if c:
            c["score"] = round(graph_base_score - i * 0.001, 4)
            c["source"] = "graph"
            c["entities"] = entity_map.get(c["id"], [])
            added.append(c)

    ctx.intermediate["graph_results"] = added
    logger.info(f"[step:graph_recall] LLM 过滤后保留 {len(added)} 条")
    for r in added:
        logger.info(f"  └─ {r.get('id','')[:8]} | {r.get('text','')[:80]}")


def _make_step():
    """创建 GraphRecall StepDef"""
    from ...context import StepDef
    return StepDef(
        name="graph_recall",
        description="共现召回 + LLM 过滤",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=30.0,
    )
