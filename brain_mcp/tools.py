"""
MCP Tools - 通过 Flask API 调用，不直接加载模型或连接 Qdrant
"""
import logging
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:18765"


def _call(path: str, data: dict) -> dict:
    """调用 Flask API"""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        API_BASE + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Memory服务未启动，请先运行 start_qdrant.bat: {e}")


def store_memory(text: str) -> str:
    result = _call("/store", {"text": text})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("result", "已记住")


def search_memory(query: str) -> list[dict]:
    result = _call("/search", {"query": query})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("results", [])


def delete_memory(memory_id: str) -> str:
    result = _call("/delete", {"memory_id": memory_id})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("result", "已删除")


def update_memory(memory_id: str, new_text: str) -> str:
    result = _call("/update", {"memory_id": memory_id, "new_text": new_text})
    if "error" in result:
        return f"错误: {result['error']}"
    return result.get("result", "已更新")


def organize_memories(query: str) -> dict:
    """Organize memories by query.

    Args:
        query: Search query to find related memories

    Returns:
        Organized memories result dictionary
    """
    result = _call("/organize", {"query": query})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result
