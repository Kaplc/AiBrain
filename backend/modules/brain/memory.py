"""
记忆核心逻辑 - 直接操作 Qdrant 和 Embedding
从 brain_mcp/_core.py 迁移至此，后端专用
"""
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PointIdsList, SearchParams
import uuid
import math
import threading
import logging

from brain_mcp.config import settings
from brain_mcp.embedding import encode_texts

_client = None
_mock_now = None  # 测试用：注入模拟时钟

logger = logging.getLogger(__name__)


def _now():
    """获取当前时间，测试时可注入 _mock_now"""
    return _mock_now() if _mock_now else datetime.now()


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.qdrant_host,
            grpc_port=settings.grpc_port,
            prefer_grpc=True,
            check_compatibility=False,
        )
        _ensure_collection()
    return _client


def _ensure_collection():
    client = _client
    collections = [c.name for c in client.get_collections().collections]
    if settings.collection_name not in collections:
        client.create_collection(
            collection_name=settings.collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE
            )
        )
    _migrate_existing()


def _migrate_existing():
    """一次性为旧记忆补充 hit_count / last_hit_at 字段"""
    try:
        client = get_client()
        results, _ = client.scroll(collection_name=settings.collection_name, limit=10000)
        for r in results:
            if "hit_count" not in r.payload:
                client.set_payload(
                    collection_name=settings.collection_name,
                    payload={"hit_count": 0, "last_hit_at": None},
                    points=[r.id]
                )
    except Exception as e:
        logger.warning(f"Migration skipped: {e}")


def _hit_memory(memory_ids: list):
    """对指定记忆列表 hit_count++，last_hit_at 更新

    - 记忆库 < 20 条时：静默跳过（兼容首次存入时的 fake id）
    - 记忆库 >= 20 条时：必须全部是有效 id，否则抛 ValueError
    """
    client = get_client()
    # 检查库记录数
    info = client.get_collection(settings.collection_name)
    skip_invalid = info.points_count < 20

    now = _now().isoformat()
    for memory_id in memory_ids:
        try:
            existing = client.retrieve(collection_name=settings.collection_name, ids=[memory_id])
        except Exception:
            # 无效 UUID 格式等错误
            if skip_invalid:
                continue  # 库不够20条时静默跳过
            raise ValueError(f"无效的 memory_id: {memory_id}")

        if not existing:
            if skip_invalid:
                continue  # 库不够20条时静默跳过
            raise ValueError(f"memory_id 不存在: {memory_id}")

        current = existing[0].payload
        client.set_payload(
            collection_name=settings.collection_name,
            payload={
                "hit_count": current.get("hit_count", 0) + 1,
                "last_hit_at": now
            },
            points=[memory_id]
        )


def _calculate_decay_score(cosine_score, hit_count, last_hit_at, lambda_decay):
    """衰减评分：cosine × log(hit_count+1) × exp(-λ × 天数)"""
    hit_factor = math.log(hit_count + 1) if hit_count > 0 else 0.1
    if last_hit_at:
        days = (_now() - datetime.fromisoformat(last_hit_at)).total_seconds() / 86400
    else:
        days = 0.0
    return cosine_score * hit_factor * math.exp(-lambda_decay * days)


def cleanup_forgotten():
    """清理衰减分低于阈值的记忆（模拟完全遗忘）"""
    FORGET_THRESHOLD = 0.001  # 衰减分低于此值视为遗忘
    try:
        client = get_client()
        now = _now()
        results, _ = client.scroll(collection_name=settings.collection_name, limit=10000)
        forgotten_ids = []
        for r in results:
            p = r.payload
            hit_count = p.get("hit_count", 0)
            last_hit = p.get("last_hit_at")
            ts = p.get("timestamp")

            if last_hit:
                last_active = datetime.fromisoformat(last_hit)
            elif ts:
                last_active = datetime.fromisoformat(ts)
            else:
                last_active = now

            days_idle = (now - last_active).total_seconds() / 86400
            # 用公式计算衰减因子（假设最高 cosine=1）
            hit_factor = math.log(hit_count + 1) if hit_count > 0 else 0.1
            decay_factor = hit_factor * math.exp(-settings.decay_lambda * days_idle)

            if decay_factor < FORGET_THRESHOLD:
                forgotten_ids.append(r.id)

        if forgotten_ids:
            client.delete(
                collection_name=settings.collection_name,
                points_selector=forgotten_ids
            )
            logger.info(f"Cleanup: removed {len(forgotten_ids)} forgotten memories")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")


def start_cleanup_loop():
    """后台定时清理遗忘记忆（每小时检查一次）"""
    def _loop():
        import time
        while True:
            time.sleep(3600)
            cleanup_forgotten()
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    logger.info("Cleanup loop started (every 1h)")


def store_memory(text: str, hit_ids: list = None) -> str:
    client = get_client()
    vector = encode_texts([text])[0]
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "text": text,
            "timestamp": _now().isoformat(),
            "hit_count": 0,
            "last_hit_at": None
        }
    )
    client.upsert(collection_name=settings.collection_name, points=[point])
    if hit_ids:
        _hit_memory(hit_ids)
    return f"已记住: {text}"


def search_memory(query: str) -> list[dict]:
    client = get_client()
    query_vector = encode_texts([query])[0]
    fetch_limit = settings.top_k * settings.search_limit_multiplier
    results = client.query_points(
        collection_name=settings.collection_name,
        query=query_vector,
        limit=fetch_limit,
        search_params=SearchParams(exact=False)
    )
    scored = []
    for r in results.points:
        payload = r.payload
        scored.append({
            "id": str(r.id),
            "text": payload.get("text", ""),
            "timestamp": payload.get("timestamp"),
            "score": round(r.score, 4),
            "decay_score": round(_calculate_decay_score(
                r.score,
                payload.get("hit_count", 0),
                payload.get("last_hit_at"),
                settings.decay_lambda
            ), 4),
            "hit_count": payload.get("hit_count", 0),
            "last_hit_at": payload.get("last_hit_at")
        })
    scored.sort(key=lambda x: x["decay_score"], reverse=True)
    return scored[:settings.top_k]


def list_memories(offset: int = 0, limit: int = 200) -> list[dict]:
    client = get_client()
    results, next_page_offset = client.scroll(
        collection_name=settings.collection_name,
        offset=offset,
        limit=limit
    )
    memories = [
        {
            "id": str(r.id),
            "text": r.payload.get("text", ""),
            "timestamp": r.payload.get("timestamp"),
            "hit_count": r.payload.get("hit_count", 0),
            "last_hit_at": r.payload.get("last_hit_at"),
            "decay_score": round(_calculate_decay_score(
                1.0,
                r.payload.get("hit_count", 0),
                r.payload.get("last_hit_at"),
                settings.decay_lambda
            ), 4)
        }
        for r in results
    ]
    memories.sort(key=lambda x: x["decay_score"], reverse=True)
    return memories


def delete_memory(memory_id: str) -> str:
    client = get_client()
    client.delete(
        collection_name=settings.collection_name,
        points_selector=PointIdsList(points=[memory_id])
    )
    return f"已删除记忆: {memory_id}"


def update_memory(memory_id: str, new_text: str) -> str:
    """更新指定记忆的内容，降低 hit_count（内容更新后引用关联减弱）"""
    client = get_client()

    try:
        existing = client.retrieve(
            collection_name=settings.collection_name,
            ids=[memory_id]
        )
    except Exception:
        existing = []

    if not existing:
        return f"错误: 记忆 ID 不存在: {memory_id}"

    vector = encode_texts([new_text])[0]
    current = existing[0].payload
    # hit_count 降低为原来的一半
    new_hit_count = max(0, int(current.get("hit_count", 0) * 0.5))
    client.upsert(
        collection_name=settings.collection_name,
        points=[PointStruct(
            id=memory_id,
            vector=vector,
            payload={
                "text": new_text,
                "timestamp": _now().isoformat(),
                "hit_count": new_hit_count,
                "last_hit_at": None
            }
        )]
    )
    return f"已更新记忆: {new_text}"


def organize_memories(query: str) -> dict:
    """搜索相关记忆并整理"""
    from .organizer import organize_memories as _organize

    related = search_memory(query)
    result = _organize(query, related)

    for mem_id in result["deleted_ids"]:
        delete_memory(mem_id)

    new_ids = []
    for mem in result.get("individual_memories", []):
        new_id = store_memory(mem["text"])
        new_ids.append(new_id.split(": ")[-1] if ": " in new_id else new_id)

    result["new_memory_ids"] = new_ids
    result["new_memory_id"] = new_ids[0] if new_ids else None

    return result
