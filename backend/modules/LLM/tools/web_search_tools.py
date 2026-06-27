"""web_search 工具 — 互联网搜索（T033 / FR-017）

通过 bash 工具（curl）抓取 DuckDuckGo Lite 搜索结果，正则提取标题+摘要+URL。
无 API key、无额外依赖。结果格式标准化供 LLM / 大脑使用。

复用 bash 工具的安全机制（命令白名单 + timeout + 输出截断）。
"""
from __future__ import annotations

import logging
import re
import urllib.parse

logger = logging.getLogger("tools.web_search")

_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/?q={query}"
_DEFAULT_MAX_RESULTS = 5


def _web_search_fn(query: str, max_results: int = _DEFAULT_MAX_RESULTS) -> str:
    """搜索互联网，返回摘要列表。"""
    if not query or not isinstance(query, str):
        return "错误: query 不能为空"

    # 通过 bash 工具执行 curl
    encoded = urllib.parse.quote(query, safe="")
    url = _DDG_LITE_URL.format(query=encoded)
    cmd = f"curl -s -L --max-time 10 -A 'Mozilla/5.0 (compatible; AiBrain/1.0)' '{url}'"

    try:
        from .registry import get_tool_registry
        html = get_tool_registry().execute("bash", {"command": cmd, "timeout": 15})
    except Exception as e:
        return f"搜索失败: {e}"

    # 检查 bash 工具返回的错误
    if html.startswith("错误:"):
        return html

    # 解析 DDG Lite 的 HTML（表格格式）
    results = _parse_ddg_lite(html)
    if not results:
        return "未找到结果"

    lines = []
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title", "").strip() or "(无标题)"
        snippet = r.get("snippet", "").strip() or ""
        url_found = r.get("url", "")
        if snippet:
            lines.append(f"{i}. {title} — {snippet[:120]}")
        else:
            lines.append(f"{i}. {title}")
        if url_found:
            lines[-1] += f"\n   {url_found}"

    return "\n".join(lines)


def _parse_ddg_lite(html: str) -> list[dict]:
    """解析 DuckDuckGo Lite 的搜索结果 HTML（表格行格式）。"""
    results = []

    # DDG Lite 的结果在 <tr class="result"> 或 <tr> 内
    # 每行包含标题（<a>）和摘要（<td class="snippet">）
    # 搜索 class="result-link" 或直接找 a 标签

    # 按行处理：找到 class="result" 的 tr，提取标题链接和摘要
    rows = re.findall(
        r'<tr[^>]*class="[^"]*result[^"]*"[^>]*>.*?</tr>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not rows:
        # fallback: 找 tr 内的 a 标签
        rows = re.findall(
            r'<tr[^>]*>.*?</tr>',
            html, re.DOTALL,
        )

    for row in rows:
        # 标题和链接
        link_match = re.search(
            r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            row, re.DOTALL | re.IGNORECASE,
        )
        if not link_match:
            # fallback: 任意 a 标签
            link_match = re.search(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                row, re.DOTALL,
            )
        if not link_match:
            continue

        url = link_match.group(1).strip()
        title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()

        # 摘要（snippet）
        snippet_match = re.search(
            r'<td[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)</td>',
            row, re.DOTALL | re.IGNORECASE,
        )
        snippet = ""
        if snippet_match:
            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()

        # 去重（DDG 可能重复）
        if url and not any(r["url"] == url for r in results):
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

    return results


# ToolDef 定义
try:
    from .registry import ToolDef

    WEB_SEARCH_TOOL = ToolDef(
        name="web_search",
        description="在互联网搜索信息。当需要了解新话题、查证事实时使用，返回标题/摘要/链接列表。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如 'Python asyncio 教程'",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"最多返回结果数（默认 {_DEFAULT_MAX_RESULTS}）",
                    "default": _DEFAULT_MAX_RESULTS,
                },
            },
            "required": ["query"],
        },
        fn=_web_search_fn,
    )
except ImportError as e:
    logger.warning(f"[web_search_tools] ToolDef import failed: {e}")
    WEB_SEARCH_TOOL = None


def register_web_search_tools():
    """注册 web_search 工具到 ToolRegistry"""
    if WEB_SEARCH_TOOL is None:
        logger.error("[web_search_tools] WEB_SEARCH_TOOL 未定义，跳过注册")
        return
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(WEB_SEARCH_TOOL)
    logger.info("[web_search_tools] 已注册 web_search 工具")
