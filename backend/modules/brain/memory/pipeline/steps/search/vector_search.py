"""
VectorSearch Step - 语义向量搜索（required）
通过统一接口层 memory_search() 自适应搜索（新库 aibrain_memories + 老库 mem0_memories 合并）

写入 ctx.intermediate:
  - semantic_results: 语义搜索结果列表 [{id, text, score, source: "semantic"}]
  - min_semantic_score: 语义结果中的最低分
"""
import logging

from modules.brain.memory.core import _get_search_options
from modules.brain.memory.store import memory_search

logger = logging.getLogger('memory.pipeline')


def _push_step(step: str, status: str):
    """向 ChatManager 推送步骤事件，供 SSE 流推送到前端"""
    try:
        from modules.chat import ChatManager
        ChatManager.get_instance().push_memory_step(step, status)
    except Exception:
        pass


def execute(ctx) -> None:
    """执行 VectorSearch 步骤：语义向量搜索 → 写入 intermediate 供后续图扩散

    纯向量搜索，不做 LLM 判断/筛选。下游 graph_recall 步骤负责图扩散补充。

    Args:
        ctx: PipelineContext
            input_data: str (query)
    """
    _push_step("vector_search", "running")
    query = ctx.input_data
    opts = _get_search_options()

    threshold = opts.get("threshold", 0.55)
    MIN_COUNT = 15

    # 第一次请求：只拿高于阈值的（memory_search 内部合并新库 aibrain_memories + 老库 mem0_memories）
    memories = memory_search(query, top_k=15, threshold=threshold)
    memories.sort(key=lambda x: x["score"], reverse=True)

    # 不足 MIN_COUNT 时，去掉阈值再请求补足
    if len(memories) < MIN_COUNT:
        result2 = memory_search(query, top_k=MIN_COUNT, threshold=0.0)
        seen_ids = {m["id"] for m in memories}
        for r in result2:
            if r.get("id") not in seen_ids:
                memories.append(r)
                seen_ids.add(r.get("id"))
        memories.sort(key=lambda x: x["score"], reverse=True)
        memories = memories[:MIN_COUNT]

    # 计算 min_semantic_score
    semantic_scores = [m["score"] for m in memories if m.get("source") == "semantic"]
    min_semantic = min(semantic_scores) if semantic_scores else 0.5

    # 打印向量搜索结果
    logger.info(f"[step:vector_search] 向量搜索结果共 {len(memories)} 条")
    for m in memories:
        logger.info(f"  └─ [{m.get('score',0):.4f}] {m.get('id','')[:8]} | {m.get('text','')[:80]}")

    # 写入 intermediate
    ctx.intermediate["semantic_results"] = memories
    ctx.intermediate["min_semantic_score"] = min_semantic
    ctx.metadata["_search_query"] = query

    logger.info(f"[step:vector_search] results={len(memories)} min_score={min_semantic:.4f}")
    _push_step("vector_search", "done")


def _make_step():
    """创建 VectorSearch StepDef"""
    from ...context import StepDef
    return StepDef(
        name="vector_search",
        description="语义向量搜索（required）",
        execute=execute,
        enabled=True,
        required=True,
        pipeline="search",
        timeout=30.0,
    )
