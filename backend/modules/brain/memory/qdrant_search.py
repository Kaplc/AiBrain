"""
Qdrant 直连搜索 - 查询新旧两个 collection

被统一接口层 store.memory_search() 调用：
  - search_new_collection():  查 aibrain_memories（新库，文本在 text 字段，payload 完整）
  - search_legacy_collection(): 查 mem0_memories（老库，文本在 data 字段，只读）

两者返回结构统一为 {id, text, score, source}，下游无感区分新旧。
collection 不存在时安全返回 []（首次运行 aibrain_memories 尚未创建）。
复用 qdrant_store 的 client / embed_texts / collection_exists，避免重复实现。
"""
import logging

logger = logging.getLogger('memory.store')

# 统一返回字段：下游只看 {id, text, score, source}，新旧无别
SOURCE_SEMANTIC = "semantic"


def _embed_query(query: str) -> list[float]:
    """单条 query 向量化"""
    from .qdrant_store import embed_texts
    return embed_texts([query])[0]


def _search_collection(collection_name: str, query_vector, top_k: int, threshold: float) -> list:
    """底层搜索：指定 collection → 命中列表

    collection 不存在时返回 []（避免首次运行报错）。
    """
    from .qdrant_store import get_qdrant_client, collection_exists, _invalidate_collection_cache

    if not collection_exists(collection_name):
        return []

    client = get_qdrant_client()
    # 本项目 qdrant_client 版本用 query_points（旧 client.search 已移除）
    try:
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            score_threshold=threshold if threshold and threshold > 0 else None,
        )
        return response.points
    except Exception as e:
        # 缓存可能过期（collection 被外部删除）→ 刷新；确实不存在则返回空，否则重新抛出
        _invalidate_collection_cache()
        if collection_exists(collection_name):
            raise
        logger.warning(f"[qdrant_search] collection '{collection_name}' missing on query: {e}")
        return []


def search_new_collection(query: str, top_k: int = 75, threshold: float = 0.0) -> list[dict]:
    """搜新 collection（aibrain_memories），文本在 text 字段，payload 完整

    返回附带 payload，供未来按 emotion/scene 等维度过滤（Phase 0）。
    """
    from .qdrant_store import NEW_COLLECTION

    query_vector = _embed_query(query)
    hits = _search_collection(NEW_COLLECTION, query_vector, top_k, threshold)

    results = []
    for hit in hits:
        payload = hit.payload or {}
        results.append({
            "id": str(hit.id),
            "text": payload.get("text", ""),
            "score": round(hit.score, 4),
            "source": SOURCE_SEMANTIC,
            "payload": payload,
        })
    logger.info(f"[qdrant_search] new collection hits={len(results)} (top_k={top_k}, threshold={threshold})")
    return results


def search_legacy_collection(query: str, top_k: int = 75, threshold: float = 0.0) -> list[dict]:
    """搜老 collection（mem0_memories，只读），data 字段映射为 text"""
    from .qdrant_store import LEGACY_COLLECTION

    query_vector = _embed_query(query)
    hits = _search_collection(LEGACY_COLLECTION, query_vector, top_k, threshold)

    results = []
    for hit in hits:
        payload = hit.payload or {}
        # mem0 的记忆文本存在 data 字段；兜底 text 字段
        text = payload.get("data", "") or payload.get("text", "")
        results.append({
            "id": str(hit.id),
            "text": text,
            "score": round(hit.score, 4),
            "source": SOURCE_SEMANTIC,
        })
    logger.info(f"[qdrant_search] legacy collection hits={len(results)} (top_k={top_k}, threshold={threshold})")
    return results
