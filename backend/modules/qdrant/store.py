"""
Qdrant 直连存储底层 - 嵌入 + 写入新 collection

被统一接口层 store.memory_store() 调用，封装：
  - QdrantClient 单例（复用 brain_mcp.config 的连接配置）
  - embed_texts()（复用 brain_mcp.embedding，走 embed_server）
  - ensure_collection()（懒创建 aibrain_memories）
  - store_vector()（嵌入单条文本 → upsert → 返回 point id）

本模块是 qdrant/search.py 与 store.py 共享的底层，避免重复实现。
"""
import logging
import threading
import uuid
from datetime import datetime, timezone

logger = logging.getLogger('memory.store')

# 新 collection：新记忆写入这里，payload 完整（text + emotion + scene + ...）
NEW_COLLECTION = "aibrain_memories"
# 老 collection：mem0 历史数据，只读，文本存在 data 字段
LEGACY_COLLECTION = "mem0_memories"

# 默认 user_id（与 mem0 保持一致，单用户系统）
DEFAULT_USER_ID = "default"

_client = None
_client_lock = threading.Lock()

# 已知存在的 collection 名缓存（避免每次搜索都 get_collections）
_collections_cache: set | None = None
_collections_lock = threading.Lock()


def get_qdrant_client():
    """单例 QdrantClient（grpc 优先，复用 brain_settings 端口）"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from qdrant_client import QdrantClient
                from brain_mcp.config import settings as brain_settings
                _client = QdrantClient(
                    host=brain_settings.qdrant_host,
                    grpc_port=brain_settings.grpc_port,
                    prefer_grpc=True,
                    check_compatibility=False,
                )
                logger.info(
                    f"[qdrant_store] client created (host={brain_settings.qdrant_host}, "
                    f"grpc_port={brain_settings.grpc_port})"
                )
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """文本向量化，复用 brain_mcp.embedding（走 embed_server，失败降级 hash）"""
    from brain_mcp.embedding import encode_texts
    return encode_texts(texts)


def _get_dim() -> int:
    """嵌入维度（来自 brain_settings）"""
    from brain_mcp.config import settings as brain_settings
    return brain_settings.embedding_dim


def _list_collections() -> set:
    """获取并缓存已存在的 collection 名集合"""
    global _collections_cache
    if _collections_cache is not None:
        return _collections_cache
    with _collections_lock:
        if _collections_cache is None:
            try:
                client = get_qdrant_client()
                _collections_cache = {c.name for c in client.get_collections().collections}
            except Exception as e:
                logger.warning(f"[qdrant_store] get_collections failed: {e}")
                _collections_cache = set()
        return _collections_cache


def _invalidate_collection_cache():
    """创建 collection 后清空缓存，下次重新拉取"""
    global _collections_cache
    _collections_cache = None


def ensure_collection():
    """确保 aibrain_memories collection 存在（懒创建，幂等）

    cosine 距离 + 1024 维（bge-m3），与 mem0_memories 维度一致。
    """
    if NEW_COLLECTION in _list_collections():
        return
    try:
        from qdrant_client.http import models as qmodels
        client = get_qdrant_client()
        client.create_collection(
            collection_name=NEW_COLLECTION,
            vectors_config=qmodels.VectorParams(
                size=_get_dim(),
                distance=qmodels.Distance.COSINE,
            ),
        )
        _invalidate_collection_cache()
        logger.info(f"[qdrant_store] created collection '{NEW_COLLECTION}' (dim={_get_dim()}, cosine)")
    except Exception as e:
        # 并发创建时可能已存在，刷新缓存后重新校验
        _invalidate_collection_cache()
        if NEW_COLLECTION not in _list_collections():
            logger.error(f"[qdrant_store] ensure_collection failed: {e}")
            raise


def collection_exists(name: str) -> bool:
    """判断某个 collection 是否已存在（走缓存）"""
    return name in _list_collections()


# ── 语义节点集合（aibrain_nodes）───────────────────────────────
NODE_COLLECTION = "aibrain_nodes"
_NODE_DEDUP_THRESHOLD = 0.85


def ensure_node_collection():
    """确保 aibrain_nodes collection 存在（懒创建，幂等）

    存储每个节点的 name 向量，用于 LLM 生成节点名的语义去重。
    """
    if NODE_COLLECTION in _list_collections():
        return
    try:
        from qdrant_client.http import models as qmodels
        client = get_qdrant_client()
        client.create_collection(
            collection_name=NODE_COLLECTION,
            vectors_config=qmodels.VectorParams(
                size=_get_dim(),
                distance=qmodels.Distance.COSINE,
            ),
        )
        _invalidate_collection_cache()
        logger.info(f"[qdrant_store] created collection '{NODE_COLLECTION}'")
    except Exception as e:
        _invalidate_collection_cache()
        if NODE_COLLECTION not in _list_collections():
            logger.error(f"[qdrant_store] ensure_node_collection failed: {e}")
            raise


def dedup_node_name(name: str, nd_type: str) -> str:
    """向量比对同类型已有节点，去重返回规范名；不存在则插入新节点

    先按 type 过滤（person/concept/emotion/goal），再向量比对，
    避免跨类型误合并（如名为"成长"的人 vs 概念"成长"）。

    Args:
        name: LLM 生成的节点名
        nd_type: 节点类型

    Returns:
        去重后的规范节点名
    """
    client = get_qdrant_client()
    ensure_node_collection()

    from qdrant_client.http import models as qmodels

    vector = embed_texts([name])[0]
    hits = client.query_points(
        collection_name=NODE_COLLECTION,
        query=vector,
        query_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="type", match=qmodels.MatchValue(value=nd_type))]
        ),
        limit=1,
        score_threshold=_NODE_DEDUP_THRESHOLD,
    )
    if hits.points:
        matched = (hits.points[0].payload or {}).get("name", name)
        logger.info(f"[node:dedup] {name} → {matched} (score={hits.points[0].score:.3f})")
        return matched

    # 未匹配 → 插入新节点（Qdrant 需要 UUID 格式 ID，用 UUID5 确定性映射）
    import uuid
    node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{nd_type}:{name}"))
    client.upsert(
        collection_name=NODE_COLLECTION,
        points=[qmodels.PointStruct(
            id=node_id, vector=vector, payload={"name": name, "type": nd_type}
        )],
        wait=True,
    )
    return name


def store_vector(text: str, payload: dict | None = None) -> str:
    """嵌入 → upsert 到 aibrain_memories → 返回 point id

    嵌入源与展示文本的来源（情景记忆 vs 普通记忆）：
      - 情景记忆（payload 含 display_text/embedding_text）：
          展示 text = display_text，向量从 embedding_text（整段情景）
      - 普通记忆（无 display_text）：展示 text = 传入 text，向量从 text（原文）

    Args:
        text: 记忆文本（普通记忆的原文 / 情景记忆的原始输入，会被 display_text 覆盖）
        payload: 完整元数据

    Returns:
        新记忆的 point id（uuid 字符串）
    """
    from qdrant_client.http import models as qmodels

    ensure_collection()

    # 展示文本：情景记忆用 display_text，普通用 text
    display_text = (payload or {}).get("display_text")
    # 嵌入源：情景用 embedding_text，否则展示文本，否则原文
    embed_source = (payload or {}).get("embedding_text") or display_text or text

    vector = embed_texts([embed_source])[0]
    point_id = str(uuid.uuid4())

    # 组装 payload：text 字段（展示标题）+ 调用方传入的元数据 + 必备字段
    full_payload = {}
    if payload:
        full_payload.update(payload)
    full_payload["text"] = display_text if display_text else text
    # display_text 已冗余（text 字段已覆盖），去除避免 payload 重复
    full_payload.pop("display_text", None)
    full_payload.setdefault("user_id", DEFAULT_USER_ID)
    full_payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    client = get_qdrant_client()
    try:
        client.upsert(
            collection_name=NEW_COLLECTION,
            points=[qmodels.PointStruct(id=point_id, vector=vector, payload=full_payload)],
            wait=True,
        )
    except Exception as e:
        # 缓存可能过期（collection 被外部删除/重建）→ 刷新缓存，确实缺失则重建后重试一次
        _invalidate_collection_cache()
        if NEW_COLLECTION not in _list_collections():
            logger.warning(f"[qdrant_store] collection missing on upsert, recreating: {e}")
            ensure_collection()
            client.upsert(
                collection_name=NEW_COLLECTION,
                points=[qmodels.PointStruct(id=point_id, vector=vector, payload=full_payload)],
                wait=True,
            )
        else:
            # collection 仍在，是其它错误，向上抛出
            raise
    import json as _j
    _log_payload = dict(full_payload)
    if _log_payload.get("embedding_text"):
        _log_payload["embedding_text"] = str(_log_payload["embedding_text"])[:120]
    logger.info(
        f"[qdrant_store] stored point={point_id[:8]}\n"
        f"{_j.dumps(_log_payload, ensure_ascii=False, indent=2)}\n"
        f"---"
    )
    return point_id
