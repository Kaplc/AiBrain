"""
统一接口层 - 管线与后端存储的唯一边界

管线步骤只调本模块的 memory_store() / memory_search()，不关心后端是谁：
  - 存储：当前走 Qdrant 直连（aibrain_memories，完整 payload）
  - 搜索：新库 aibrain_memories + 老库 mem0_memories 合并返回

未来移除 mem0：只需删掉 memory_search 里对 search_legacy_collection 的调用，
管线代码一行不改。切换其它后端：在 memory_store 里加分发逻辑即可。
"""
import logging

logger = logging.getLogger('memory.store')


def memory_store(text: str, payload: dict | None = None) -> dict:
    """统一存储接口：嵌入 → 存入 aibrain_memories → 返回 mem0 兼容结果

    纯存储层：不做 LLM 事实抽取 / 写时去重（那是 Phase 0 MemoryEncoder 的职责，
    见 .claude/plan/merged-memory-plan/01-记忆编码升级.md）。
    返回结构与 mem0.add() 一致，下游步骤（entity_extract/graph_link/event_extract）无感。

    Args:
        text: 记忆文本
        payload: 完整元数据（category / emotion / scene / temperature / hooks 等）

    Returns:
        {"results": [{"event": "ADD", "id": <point_id>, "memory": <text>}]}
    """
    from modules.qdrant.store import store_vector

    logger.info(f"[memory_store] START | text={text[:60]!r} | payload_keys={list(payload.keys()) if payload else []}")
    point_id = store_vector(text, payload=payload)
    logger.info(f"[memory_store] DONE | point_id={point_id[:8]}")

    # 包成 mem0.add() 兼容的事件结构，下游解析 ADD/UPDATE/DELETE 无感
    return {
        "results": [
            {"event": "ADD", "id": point_id, "memory": text},
        ],
    }


def memory_search(query: str, top_k: int = 75, threshold: float = 0.0) -> list[dict]:
    """统一搜索接口：新库 + 老库合并，去重排序

    Args:
        query: 搜索文本
        top_k: 每个 collection 的返回上限（合并后上限为 2*top_k）
        threshold: 相似度阈值，>0 时过滤 score < threshold 的结果

    Returns:
        [{id, text, score, source, payload?}, ...] 按 score 降序、id 去重
    """
    from modules.qdrant.search import search_new_collection, search_legacy_collection

    results: list[dict] = []

    # 1. 搜新 collection（aibrain_memories）
    try:
        results.extend(search_new_collection(query, top_k=top_k, threshold=threshold))
    except Exception as e:
        logger.warning(f"[memory_search] new collection search failed: {e}")

    # 2. 搜老 collection（mem0_memories，只读）—— 移除 mem0 时删掉这段即可
    try:
        results.extend(search_legacy_collection(query, top_k=top_k, threshold=threshold))
    except Exception as e:
        logger.warning(f"[memory_search] legacy collection search failed: {e}")

    # 3. 去重 + 排序
    merged = _merge_results(results)
    logger.info(f"[memory_search] query={query[:40]!r} | merged={len(merged)} (new+legacy={len(results)})")
    return merged


def _merge_results(results: list[dict]) -> list[dict]:
    """合并搜索结果：按 id 去重（重复 id 保高分），按 score 降序"""
    seen: dict = {}
    for r in results:
        rid = r.get("id")
        if rid is None:
            continue
        if rid not in seen or r.get("score", 0) > seen[rid].get("score", 0):
            seen[rid] = r
    return sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
