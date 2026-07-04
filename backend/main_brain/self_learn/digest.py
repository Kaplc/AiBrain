"""搜索与提炼 — web_search → web_fetch → 内容摘要"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("self_learn.digest")


def search_and_digest(topic: str, max_chars: int = 3000) -> str:
    """搜索 topic 并提炼为摘要。

    流程: web_search 搜 → 取首条 url → web_fetch 抓 → 提炼摘要。
    每一步失败都降级而不是崩溃。
    """
    if not topic:
        return ""

    try:
        from main_brain.adapters.tools import get_tool_adapter
        tools = get_tool_adapter()
    except Exception as e:
        logger.warning(f"[digest] tool_adapter not available: {e}")
        return _fallback_summary(topic)

    # 1. web_search
    try:
        search_result = tools.call("web_search", {"query": topic, "max_results": 3})
    except Exception as e:
        logger.warning(f"[digest] web_search failed: {e}")
        return _fallback_summary(topic)

    if not search_result or search_result.startswith(("错误", "搜索失败")) or "未找到结果" in search_result:
        logger.info(f"[digest] web_search no result for '{topic}': {search_result[:60]}")
        return _fallback_summary(topic)

    # 2. 从搜索结果中提取首条 URL
    url = _extract_first_url(search_result)
    if not url:
        logger.info(f"[digest] no url in search result for '{topic}'")
        return _fallback_summary(topic)

    # 3. web_fetch
    try:
        fetch_result = tools.call("web_fetch", {"url": url, "max_chars": max_chars})
    except Exception as e:
        logger.warning(f"[digest] web_fetch failed: {e}")
        return _fallback_summary(topic)

    if not fetch_result or fetch_result.startswith("错误"):
        return _fallback_summary(topic)

    # 4. 提炼：取前 800 字符作为摘要（MVP 简单截取，后续可升级为 LLM 提炼）
    cleaned = re.sub(r'\s+', ' ', fetch_result).strip()
    if len(cleaned) > 800:
        return cleaned[:800] + "..."
    return cleaned


def _extract_first_url(text: str) -> str | None:
    """从 web_search 结果文本中提取首条 URL。"""
    # 匹配 http/https URL
    urls = re.findall(r'https?://[^\s\)\]>"]+', text)
    for u in urls:
        # 过滤掉无意义 URL
        if u and not u.endswith('.ico') and 'duckduckgo' not in u:
            return u
    return None


def _fallback_summary(topic: str) -> str:
    """搜索失败时的降级摘要：直接用 topic 本身。"""
    return f"关于「{topic}」的学习记录"
