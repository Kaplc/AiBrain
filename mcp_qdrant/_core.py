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
    ]


def list_memories() -> list[dict]:
    client = get_client()
    results = client.scroll(
        collection_name=settings.collection_name,
        limit=200
    )[0]
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
