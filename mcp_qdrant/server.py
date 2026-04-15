from fastmcp import FastMCP

from .tools import store_memory, search_memory, list_memories, delete_memory

mcp = FastMCP("Qdrant Memory Server")


@mcp.tool()
def store(text: str) -> str:
    """Store a memory from user input.

    Args:
        text: The memory text to store

    Returns:
        Confirmation message
    """
    return store_memory(text)


@mcp.tool()
def search(query: str) -> list[dict]:
    """Search memories by query.

    Args:
        query: The search query

    Returns:
        List of matching memories with scores
    """
    return search_memory(query)


@mcp.tool()
def list_all() -> list[dict]:
    """List all stored memories.

    Returns:
        List of all memories
    """
    return list_memories()


@mcp.tool()
def delete(memory_id: str) -> str:
    """Delete a memory by ID.

    Args:
        memory_id: The memory ID to delete

    Returns:
        Confirmation message
    """
    return delete_memory(memory_id)
