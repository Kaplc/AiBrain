"""
VectorSearch Step - 语义向量搜索（required）
通过统一接口层 memory_search() 自适应搜索（新库 aibrain_memories + 老库 mem0_memories 合并）

写入 ctx.intermediate:
  - semantic_results: 语义搜索结果列表 [{id, text, score, source: "semantic"}]
  - min_semantic_score: 语义结果中的最低分
"""
import logging

from modules.brain.memory.store import memory_search


def _set_status(s: str):
    try:
        from modules.chat import ChatManager
        ChatManager.get_instance().set_status(s)
    except Exception:
        pass
from modules.brain.memory.core import _get_search_options

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 VectorSearch 步骤：自适应语义搜索

    Args:
        ctx: PipelineContext
            input_data: str (query)
    """
    _set_status("向量搜索")
    query = ctx.input_data
    opts = _get_search_options()

    threshold = opts.get("threshold", 0.55)
    MIN_COUNT = 15

    # 第一次请求：只拿高于阈值的（memory_search 内部合并新库 aibrain_memories + 老库 mem0_memories）
    memories = memory_search(query, top_k=75, threshold=threshold)
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

    # 先判断搜索结果是否足够回答（不筛选，用原始结果判断）
    ctx.metadata["_info_enough"] = False
    if memories:
        try:
            from modules.LLM import get_agent_manager
            agent = get_agent_manager().get("info_sufficient")
            verdict = agent.run({"query": query, "memories": memories})
            if verdict.get("enough"):
                ctx.metadata["_info_enough"] = True
                logger.info("[step:vector_search] info_sufficient=true，跳过筛选，直接回复")
            else:
                logger.info(f"[step:vector_search] info_sufficient=false，继续筛选")
        except Exception as e:
            logger.warning(f"[step:vector_search] info_sufficient failed: {e}")

    # 如果不够，再进行 LLM 筛选（缩小范围供下游实体扩散）
    if not ctx.metadata["_info_enough"] and memories:
        try:
            from modules.LLM import get_agent_manager
            agent = get_agent_manager().get("memory_relation")
            related_ids = agent.run({"query": query, "candidates": memories})
            if related_ids:
                id_set = set(related_ids)
                memories = [m for m in memories if m.get("id") in id_set]
                logger.info(f"[step:vector_search] LLM filter: {len(related_ids)} related kept")
                for m in memories:
                    logger.info(f"  └─ {m.get('id','')[:8]} | {m.get('text','')[:80]}")
            else:
                memories = []
                logger.info("[step:vector_search] LLM filter: none related")
        except Exception as e:
            logger.warning(f"[step:vector_search] LLM filter failed, using all results: {e}")

    # 写入 intermediate
    ctx.intermediate["semantic_results"] = memories
    ctx.intermediate["min_semantic_score"] = min_semantic
    ctx.metadata["_search_query"] = query

    logger.info(f"[step:vector_search] results={len(memories)} min_score={min_semantic:.4f}")


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
