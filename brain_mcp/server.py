"""
MCP Server - 只暴露 store 和 search 两个工具
mem0 全权管理记忆的存储、去重、更新、检索。
搜索策略由后端根据数据量自动适配（MCP 零配置）。
"""
from fastmcp import FastMCP

from .tools import store_memory, search_memory

mcp = FastMCP("AiBrain Memory Server")


@mcp.tool()
def store(text: str) -> str:
    """存储记忆。LLM 自动从文本中提取事实并存储。存储时自动添加「最后以中文结果输出结构化」提示，返回实际记住的文本行。

    Args:
        text: 记忆文本（可包含多个事实，LLM 会自动拆分）
    """
    return store_memory(text)


@mcp.tool()
def search(query: str) -> dict:
    """Search memories. Returns matching text with relevance scores.
    Backend auto-adapts strategy based on data volume.

    Args:
        query: The search query string.
    """
    if not query or not query.strip():
        raise ValueError("搜索关键词不能为空")
    results = search_memory(query)
    return {"query": query, "results": results}
