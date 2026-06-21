"""
GraphRecall Step - 共现召回（按 co_count 排序）
通过实体网络召回额外相关记忆，按共现次数排序取 topN

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


def _push_step(step: str, status: str):
    """向 ChatManager 推送步骤事件，供 SSE 流推送到前端"""
    try:
        from modules.chat import ChatManager
        ChatManager.get_instance().push_memory_step(step, status)
    except Exception:
        pass


def execute(ctx) -> None:
    _push_step("graph_recall", "running")
    _set_status("实体搜索")
    """执行 GraphRecall 步骤：实体映射 + 共现召回

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:graph_recall] infer=false, skip")
        _push_step("graph_recall", "done")
        for m in ctx.intermediate.get("semantic_results", []):
            m.setdefault("entities", [])
        return

    query = ctx.input_data
    semantic_results = ctx.intermediate.get("semantic_results")
    if semantic_results is None:
        logger.info("[step:graph_recall] no semantic_results, skip")
        _push_step("graph_recall", "done")
        return

    from modules.brain.graph import get_graph
    graph = get_graph()
    if not graph:
        logger.warning("[step:graph_recall] graph not available, skip")
        _push_step("graph_recall", "done")
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
    candidates = graph.search_related_new(mem_ids, all_entities, max_candidates=200)
    if not candidates:
        logger.info("[step:graph_recall] 扩散召回无候选记忆")
        _push_step("graph_recall", "done")
        return

    # 从 Qdrant 补 display_text（图不再存文本）
    try:
        from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
        _qc = get_qdrant_client()
        _points = _qc.retrieve(collection_name=NEW_COLLECTION, ids=[c['id'] for c in candidates])
        _text_map = {str(p.id): (p.payload or {}).get("display_text") or (p.payload or {}).get("text", "") for p in _points}
        for c in candidates:
            _t = _text_map.get(c['id'])
            if _t:
                c['text'] = _t
    except Exception:
        pass

    logger.info(f"[step:graph_recall] 共现召回 {len(candidates)} 条候选记忆 | 按 co_count 排序取 top")
    for i, c in enumerate(candidates):
        logger.info(f"[step:graph_recall] 候选[{i}] spread={c.get('spread_score',0):.3f} | {c['id'][:8]} | {c['text'][:80]}")

    # 按 spread_score 排序，保留全部候选
    candidates.sort(key=lambda x: x.get("spread_score", 0), reverse=True)
    min_semantic = ctx.intermediate.get("min_semantic_score", 0.5)
    graph_base_score = min_semantic * 0.8

    # 内部状态层偏置：concern_bias(0.005) + goal_bias(priority x 0.01)
    # 替换旧的 self_narrative goals/interests 认知加持；权重小，不会压过语义分
    _concerns_mgr = None
    _goals_mgr = None
    try:
        from modules.brain.state import get_concerns, get_goals
        _concerns_mgr = get_concerns()
        _goals_mgr = get_goals()
    except Exception:
        pass

    added = []
    for i, c in enumerate(candidates):
        c["score"] = round(graph_base_score - i * 0.001, 4)
        c["source"] = "graph"
        ents = entity_map.get(c["id"], [])
        c["entities"] = ents
        # concern + goal 偏置：命中高关注实体或目标相关概念时小幅加分
        if _concerns_mgr and _goals_mgr and ents:
            bias = _concerns_mgr.concern_bias_for_entities(ents) + _goals_mgr.goal_bias_for_entities(ents)
            if bias > 0 and graph_base_score > 0:
                # 封顶在 graph_base_score 的 15%，保证低分场景也不压语义分（决策 #4）
                bias = min(bias, graph_base_score * 0.15)
                c["score"] = min(1.0, c["score"] + bias)
        added.append(c)

    ctx.intermediate["graph_results"] = added
    logger.info(f"[step:graph_recall] 共现保留 {len(added)} 条")
    for r in added:
        logger.info(f"  └─ {r.get('id','')[:8]} | {r.get('text','')[:80]}")
    _push_step("graph_recall", "done")


def _make_step():
    """创建 GraphRecall StepDef"""
    from ...context import StepDef
    return StepDef(
        name="graph_recall",
        description="共现召回（实体扩散）",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=30.0,
    )
