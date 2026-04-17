"""
_core.py - 底层业务逻辑，直接操作 Qdrant 和 Embedding
app.py 和 MCP server 的底层实现
"""
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PointIdsList, SearchParams
import uuid
import logging

from .config import settings
from .embedding import encode_texts

_client = None

logger = logging.getLogger(__name__)


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.qdrant_host,
            grpc_port=settings.qdrant_port + 1,  # 6334
            prefer_grpc=True,
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


def store_memory(text: str) -> str:
    client = get_client()
    vector = encode_texts([text])[0]
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
    )
    client.upsert(collection_name=settings.collection_name, points=[point])
    return f"已记住: {text}"


def search_memory(query: str) -> list[dict]:
    client = get_client()
    query_vector = encode_texts([query])[0]
    results = client.query_points(
        collection_name=settings.collection_name,
        query=query_vector,
        limit=settings.top_k,
        search_params=SearchParams(exact=False)
    )
    return [
        {
            "id": str(r.id),
            "text": r.payload["text"],
            "timestamp": r.payload["timestamp"],
            "score": round(r.score, 4)
        }
        for r in results.points
        if r.score >= settings.score_threshold
    ]


def list_memories(offset: int = 0, limit: int = 200) -> list[dict]:
    client = get_client()
    results, next_page_offset = client.scroll(
        collection_name=settings.collection_name,
        offset=offset,
        limit=limit
    )
    return [
        {
            "id": str(r.id),
            "text": r.payload["text"],
            "timestamp": r.payload["timestamp"]
        }
        for r in results
    ]


def delete_memory(memory_id: str) -> str:
    client = get_client()
    client.delete(
        collection_name=settings.collection_name,
        points_selector=PointIdsList(points=[memory_id])
    )
    return f"已删除记忆: {memory_id}"


def update_memory(memory_id: str, new_text: str) -> str:
    """更新指定记忆的内容。

    Args:
        memory_id: 记忆 ID
        new_text: 新的记忆文本

    Returns:
        更新结果消息或错误提示
    """
    client = get_client()

    # 检查 ID 是否存在
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
    client.upsert(
        collection_name=settings.collection_name,
        points=[PointStruct(
            id=memory_id,
            vector=vector,
            payload={
                "text": new_text,
                "timestamp": datetime.now().isoformat()
            }
        )]
    )
    return f"已更新记忆: {new_text}"


def organize_memories(query: str) -> dict:
    """搜索相关记忆并整理。

    Args:
        query: 查询关键词

    Returns:
        整理结果字典
    """
    from ._organizer import organize_memories as _organize

    # 搜索相关记忆
    related = search_memory(query)

    # 整理
    result = _organize(query, related)

    # 删除原记忆
    for mem_id in result["deleted_ids"]:
        delete_memory(mem_id)

    # 逐条存入结构化后的记忆（而不是合并成一条）
    new_ids = []
    for mem in result.get("individual_memories", []):
        new_id = store_memory(mem["text"])
        new_ids.append(new_id.split(": ")[-1] if ": " in new_id else new_id)

    result["new_memory_ids"] = new_ids
    result["new_memory_id"] = new_ids[0] if new_ids else None

    return result
