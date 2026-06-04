"""
EventRecall Step - 事件反查 + 事件链扩展
通过事件系统召回额外相关记忆

读取 ctx.intermediate:
  - semantic_results: 语义搜索结果

写入 ctx.intermediate:
  - event_results: 事件召回的额外记忆列表
"""
import logging

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 EventRecall 步骤：事件反查 + 链扩展

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:event_recall] infer=false, skip")
        return

    query = ctx.input_data
    semantic_results = ctx.intermediate.get("semantic_results")
    if semantic_results is None:
        logger.info("[step:event_recall] no semantic_results, skip")
        return

    from modules.brain.memory.events import get_event_store
    event_store = get_event_store()
    if not event_store:
        logger.info("[step:event_recall] EventStore not available, skip")
        return

    matched_events = event_store.search_events_by_query(query, max_results=15)
    logger.info(f"[step:event_recall] LLM事件匹配 → {len(matched_events)} 条事件")

    if not matched_events:
        logger.info("[step:event_recall] no matched events")
        return

    for ev in matched_events:
        logger.info(f"[step:event_recall] matched event | {ev['subject']}→{ev['action']} | {ev['summary'][:50]}")

    # 链扩展：1 跳
    chain_event_ids = set()
    for ev in matched_events:
        chain_event_ids.add(ev["id"])
        for chain_ev in event_store.get_chain_for_event(ev["id"], max_depth=1):
            chain_event_ids.add(chain_ev["id"])
    logger.info(f"[step:event_recall] 链扩展后 → {len(chain_event_ids)} 条事件（含链）")

    # 反查关联的 memory_id
    chain_memory_ids = event_store.get_memories_for_events(list(chain_event_ids))
    logger.info(f"[step:event_recall] 关联memory_id → {len(chain_memory_ids)} 条")

    seen_ids = {m["id"] for m in semantic_results}
    new_mem_ids = [mid for mid in chain_memory_ids if mid not in seen_ids]
    logger.info(f"[step:event_recall] 去重后新记忆 → {len(new_mem_ids)} 条（已有{len(seen_ids)}条）")

    if not new_mem_ids:
        logger.info("[step:event_recall] no new memories after dedup")
        return

    # 从 graph 的 memory_nodes 表获取记忆文本
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
                    logger.info(f"[step:event_recall] fetched mem {mid[:8]} | {rows[0][1][:50]}")
                else:
                    logger.info(f"[step:event_recall] mem {mid[:8]} not in memory_nodes, skip")
    except Exception as e:
        logger.warning(f"[step:event_recall] graph lookup failed: {e}")

    if event_results:
        # 打分：min_semantic × 0.85 - i × 0.001
        min_semantic = ctx.intermediate.get("min_semantic_score", 0.5)
        base = min_semantic * 0.85
        for i, er in enumerate(event_results):
            er["score"] = round(base - i * 0.001, 4)

        ctx.intermediate["event_results"] = event_results
        logger.info(f"[step:event_recall] 事件链召回 {len(event_results)} 条新记忆 | base_score={base:.4f}")
    else:
        logger.info("[step:event_recall] no event results (graph lookup empty)")


def _make_step():
    """创建 EventRecall StepDef"""
    from ...context import StepDef
    return StepDef(
        name="event_recall",
        description="事件反查 + 事件链扩展",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=30.0,
    )
