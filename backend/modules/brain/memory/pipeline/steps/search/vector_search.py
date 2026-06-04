"""
VectorSearch Step - 语义向量搜索（required）
封装 mem0.search() 自适应搜索逻辑

写入 ctx.intermediate:
  - semantic_results: 语义搜索结果列表 [{id, text, score, source: "semantic"}]
  - min_semantic_score: 语义结果中的最低分
"""
import logging

from modules.brain.mem0_adapter import get_mem0_client
from modules.brain.memory.core import DEFAULT_USER_ID, _get_search_options

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 VectorSearch 步骤：自适应语义搜索

    Args:
        ctx: PipelineContext
            input_data: str (query)
    """
    query = ctx.input_data
    client = get_mem0_client()
    opts = _get_search_options()

    threshold = opts.get("threshold", 0.55)
    rerank = opts.get("rerank", False)
    MIN_COUNT = 15

    filters = {"user_id": DEFAULT_USER_ID}

    # 第一次请求：只拿高于阈值的
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

    # 不足 MIN_COUNT 时，去掉阈值再请求补足
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

    # 计算 min_semantic_score
    semantic_scores = [m["score"] for m in memories if m.get("source") == "semantic"]
    min_semantic = min(semantic_scores) if semantic_scores else 0.5

    # 写入 intermediate
    ctx.intermediate["semantic_results"] = memories
    ctx.intermediate["min_semantic_score"] = min_semantic

    # 也存一份到 metadata 供兼容层快速访问
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
        timeout=10.0,
    )
