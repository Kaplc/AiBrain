from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PointIdsList, SearchParams
import subprocess
import socket
import uuid
import logging

from .config import settings
from .embedding import encode_texts

_client = None
_qdrant_process = None

logger = logging.getLogger(__name__)


def _is_port_open(host: str, port: int) -> bool:
    """Check if Qdrant port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _start_qdrant_docker() -> bool:
    """Start Qdrant via Docker."""
    global _qdrant_process
    try:
        _qdrant_process = subprocess.Popen(
            ["docker", "run", "-d", "-p", "6333:6333", "-p", "6334:6334", "--name", "qdrant_memory", "qdrant/qdrant"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to start Qdrant via Docker: {e}")
        return False


def _ensure_qdrant_running():
    """Ensure Qdrant is running, start if not."""
    if _is_port_open(settings.qdrant_host, settings.qdrant_port):
        return True

    logger.info("Qdrant not running, attempting to start...")

    # Try Docker first
    if _start_qdrant_docker():
        import time
        # Wait for Qdrant to be ready
        for _ in range(30):
            time.sleep(1)
            if _is_port_open(settings.qdrant_host, settings.qdrant_port):
                logger.info("Qdrant started successfully via Docker")
                return True

    logger.error("Could not start Qdrant automatically. Please ensure Docker is running or start Qdrant manually.")
    return False


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _ensure_qdrant_running()
        _client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port
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

    client.upsert(
        collection_name=settings.collection_name,
        points=[point]
    )

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

    memories = []
    for result in results.points:
        memories.append({
            "text": result.payload["text"],
            "timestamp": result.payload["timestamp"],
            "score": round(result.score, 4)
        })

    return memories


def list_memories() -> list[dict]:
    client = get_client()

    results = client.scroll(
        collection_name=settings.collection_name,
        limit=100
    )[0]

    memories = []
    for result in results:
        memories.append({
            "id": result.id,
            "text": result.payload["text"],
            "timestamp": result.payload["timestamp"]
        })

    return memories


def delete_memory(memory_id: str) -> str:
    client = get_client()
    client.delete(
        collection_name=settings.collection_name,
        points_selector=PointIdsList(points=[memory_id])
    )
    return f"已删除记忆: {memory_id}"
