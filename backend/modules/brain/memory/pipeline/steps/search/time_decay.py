"""
TimeDecay Step - 时间衰减加权
对搜索结果应用时间衰减因子调整分数

读取 ctx.intermediate:
  - semantic_results: 语义搜索结果
  - event_results: 事件召回结果（可选）
  - graph_results: 图召回结果（可选）

直接原地修改 ctx.intermediate 内的 score 字段
"""
import logging

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 TimeDecay 步骤：基于事件的时间衰减加权

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:time_decay] infer=false, skip")
        return

    from modules.brain.memory.events import get_event_store
    event_store = get_event_store()
    if not event_store:
        logger.info("[step:time_decay] EventStore not available, skip")
        return

    # 合并所有结果
    all_memories = []
    for key in ("semantic_results", "event_results", "graph_results"):
        results = ctx.intermediate.get(key)
        if results:
            all_memories.extend(results)

    if not all_memories:
        logger.info("[step:time_decay] no memories to decay")
        return

    all_mem_ids = [m["id"] for m in all_memories if m.get("id")]
    if not all_mem_ids:
        logger.info("[step:time_decay] no valid memory IDs")
        return

    event_map = event_store.get_events_for_memories(all_mem_ids)
    has_events = sum(1 for v in event_map.values() if v)
    logger.info(f"[step:time_decay] 事件映射 → {has_events}/{len(all_mem_ids)} 条记忆有事件关联")

    if not has_events:
        logger.info("[step:time_decay] 无记忆有关联事件，跳过衰减")
        return

    # 记录衰减前后的分数变化
    before_scores = {m["id"]: m["score"] for m in all_memories if m.get("id")}

    # 使用 EventStore 的 apply_decay_to_results 方法
    # 注意：这个方法会原地修改 memories 列表中的 score
    event_store.apply_decay_to_results(all_memories, event_map)

    for m in all_memories:
        mid = m.get("id", "")
        if mid in before_scores:
            old_s = before_scores[mid]
            new_s = m["score"]
            if abs(old_s - new_s) > 0.001:
                logger.info(f"[step:time_decay] decay {mid[:8]} | {old_s:.4f} → {new_s:.4f} | source={m.get('source', '')}")

    logger.info(f"[step:time_decay] 衰减完成 | top3 scores={[m['score'] for m in all_memories[:3]]}")


def _make_step():
    """创建 TimeDecay StepDef"""
    from ...context import StepDef
    return StepDef(
        name="time_decay",
        description="时间衰减加权",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=10.0,
    )
