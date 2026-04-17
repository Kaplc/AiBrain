"""
MCP Server - 仅暴露 search 和 store
通过 Flask API 调用后端，不直接操作 Qdrant
"""
from fastmcp import FastMCP

from .tools import store_memory, search_memory

mcp = FastMCP("Qdrant Memory Server")


@mcp.tool()
def store(text: str, hit_ids: list = None) -> str:
    """Store a memory. hit_ids is a list of referenced memory IDs to increment hit_count.

    Args:
        text: The memory text to store
        hit_ids: List of existing memory IDs that were referenced (required)
    """
    return store_memory(text, hit_ids=hit_ids)


@mcp.tool()
def search(query: str) -> list[dict]:
    """Search memories by query. Returns results with decay_score.

    Args:
        query: The search query
    """
    return search_memory(query)
