"""web_search 工具 — 多后端互联网搜索（复制自 Hermes 实现）

支持后端（自动检测）：
  1. ddgs — DuckDuckGo 搜索（通过 ddgs 包，免费，无需 API key，主方案）
  2. searxng — 自建 SearXNG 实例（可选，需设置 SEARXNG_URL 环境变量）
  3. ddg_lite — DDG Lite HTML 抓取（兜底 fallback）

移除旧的 curl/bash 依赖，改用 Python httpx/ddgs 直接请求。
结果格式统一为 Hermes 风格：
  {"success": true, "data": {"web": [{"title":..., "url":..., "description":..., "position":...}]}}
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger("tools.web_search")

_DEFAULT_MAX_RESULTS = 5

# ════════════════════════════════════════════════════════════
# Provider 基类（参考 Hermes WebSearchProvider 简化版）
# ════════════════════════════════════════════════════════════


class SearchProvider(ABC):
    """搜索提供者基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """唯一标识符"""

    @abstractmethod
    def is_available(self) -> bool:
        """能否使用（检查环境变量 / 包是否可导入），不触发网络 I/O"""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """执行搜索，返回 Hermes 标准格式：
        {"success": bool, "data": {"web": [...]}}  或  {"success": false, "error": str}
        """


# ════════════════════════════════════════════════════════════
# Provider 实现
# ════════════════════════════════════════════════════════════


class DDGSProvider(SearchProvider):
    """DuckDuckGo 搜索 — 通过 ddgs 包（免 API key，主方案）

    完全复制自 Hermes plugins/web/ddgs/provider.py 的搜索逻辑，
    去掉 plugin 注册 + setup_schema 等 AiBrain 不需要的部分。
    """

    @property
    def name(self) -> str:
        return "ddgs"

    def is_available(self) -> bool:
        try:
            import ddgs  # noqa: F401
            return True
        except ImportError:
            return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            from ddgs import DDGS  # type: ignore
        except ImportError:
            return {"success": False, "error": "ddgs 包未安装，请执行 pip install ddgs"}

        safe_limit = max(1, int(limit))

        try:
            web_results = []
            with DDGS() as client:
                for i, hit in enumerate(client.text(query, max_results=safe_limit)):
                    if i >= safe_limit:
                        break
                    url = str(hit.get("href") or hit.get("url") or "")
                    web_results.append({
                        "title": str(hit.get("title", "")),
                        "url": url,
                        "description": str(hit.get("body", "")),
                        "position": i + 1,
                    })
        except Exception as exc:
            logger.warning("DDGS search error: %s", exc)
            return {"success": False, "error": f"DuckDuckGo 搜索失败: {exc}"}

        logger.info("DDGS search '%s': %d results (limit %d)", query, len(web_results), limit)
        return {"success": True, "data": {"web": web_results}}


class SearXNGProvider(SearchProvider):
    """SearXNG 搜索 — 自建实例（可选，需 SEARXNG_URL）

    复制自 Hermes plugins/web/searxng/provider.py。
    """

    @property
    def name(self) -> str:
        return "searxng"

    def is_available(self) -> bool:
        return bool(os.getenv("SEARXNG_URL", "").strip())

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        import httpx

        base_url = os.getenv("SEARXNG_URL", "").strip().rstrip("/")
        if not base_url:
            return {"success": False, "error": "SEARXNG_URL 未设置"}

        params: Dict[str, Any] = {
            "q": query,
            "format": "json",
            "pageno": 1,
        }

        try:
            resp = httpx.get(
                f"{base_url}/search",
                params=params,
                timeout=15,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("SearXNG HTTP error: %s", exc)
            return {"success": False, "error": f"SearXNG 返回 HTTP {exc.response.status_code}"}
        except httpx.RequestError as exc:
            logger.warning("SearXNG request error: %s", exc)
            return {"success": False, "error": f"无法连接 SearXNG {base_url}: {exc}"}

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning("SearXNG response parse error: %s", exc)
            return {"success": False, "error": "SearXNG 响应解析失败"}

        raw_results = data.get("results", [])
        sorted_results = sorted(
            raw_results,
            key=lambda r: float(r.get("score", 0)),
            reverse=True,
        )[:limit]

        web_results = [
            {
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "description": str(r.get("content", "")),
                "position": i + 1,
            }
            for i, r in enumerate(sorted_results)
        ]

        logger.info("SearXNG search '%s': %d results (limit %d)", query, len(web_results), limit)
        return {"success": True, "data": {"web": web_results}}


class DDGLiteProvider(SearchProvider):
    """DuckDuckGo Lite HTML 抓取 — 兜底 fallback

    保留旧的 DDG Lite 方案，但用 httpx 替代 curl/bash。
    仅在 ddgs 和 searxng 都不可用时才启用。
    """

    _DDG_LITE_URL = "https://lite.duckduckgo.com/lite/?q={query}"

    @property
    def name(self) -> str:
        return "ddg_lite"

    def is_available(self) -> bool:
        # 始终可用（纯 HTTP，无需额外依赖）
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        import httpx
        import re

        encoded = urllib.parse.quote(query, safe="")
        url = self._DDG_LITE_URL.format(query=encoded)

        try:
            resp = httpx.get(
                url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AiBrain/1.0)"},
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.RequestError as exc:
            logger.warning("DDG Lite request error: %s", exc)
            return {"success": False, "error": f"DDG Lite 请求失败: {exc}"}
        except httpx.HTTPStatusError as exc:
            logger.warning("DDG Lite HTTP error: %s", exc)
            return {"success": False, "error": f"DDG Lite HTTP {exc.response.status_code}"}

        html = resp.text
        results = _parse_ddg_lite(html)
        if not results:
            return {"success": True, "data": {"web": []}}

        web_results = [
            {
                "title": r["title"],
                "url": r["url"],
                "description": r["snippet"],
                "position": i + 1,
            }
            for i, r in enumerate(results[:limit])
        ]

        logger.info("DDG Lite search '%s': %d results (limit %d)", query, len(web_results), limit)
        return {"success": True, "data": {"web": web_results}}


# ════════════════════════════════════════════════════════════
# DDG Lite HTML 解析（保留旧逻辑，复用）
# ════════════════════════════════════════════════════════════


def _parse_ddg_lite(html: str) -> list[dict]:
    """解析 DuckDuckGo Lite 的搜索结果 HTML（表格行格式）"""
    import re

    results = []

    rows = re.findall(
        r'<tr[^>]*class="[^"]*result[^"]*"[^>]*>.*?</tr>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not rows:
        rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)

    for row in rows:
        link_match = re.search(
            r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            row, re.DOTALL | re.IGNORECASE,
        )
        if not link_match:
            link_match = re.search(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                row, re.DOTALL,
            )
        if not link_match:
            continue

        url = link_match.group(1).strip()
        title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()

        snippet_match = re.search(
            r'<td[^>]*class="[^"]*snippet[^"]*"[^>]*>(.*?)</td>',
            row, re.DOTALL | re.IGNORECASE,
        )
        snippet = ""
        if snippet_match:
            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()

        if url and not any(r["url"] == url for r in results):
            results.append({"title": title, "url": url, "snippet": snippet})

    return results


# ════════════════════════════════════════════════════════════
# 后端选择（复制自 Hermes _get_backend + _is_backend_available）
# ════════════════════════════════════════════════════════════


def _has_env(name: str) -> bool:
    val = os.getenv(name)
    return bool(val and val.strip())


def _get_all_providers() -> list[SearchProvider]:
    """返回所有已注册的 provider 实例（按优先级排序）"""
    return [
        DDGSProvider(),
        SearXNGProvider(),
        DDGLiteProvider(),
    ]


def _get_search_backend() -> SearchProvider:
    """选择可用的搜索后端。

    优先级：
      1. 环境变量 WEB_SEARCH_BACKEND 指定的后端
      2. 按优先级遍历 provider，返回第一个 is_available() 为 True 的
      3. DDGLiteProvider（兜底，始终可用）
    """
    # 1. 环境变量显式指定
    explicit = (os.getenv("WEB_SEARCH_BACKEND") or "").strip().lower()
    if explicit:
        for p in _get_all_providers():
            if p.name == explicit and p.is_available():
                logger.info("Web search backend: %s (explicit)", p.name)
                return p
        if explicit:
            logger.warning("Web search backend '%s' 指定但不可用，回退自动检测", explicit)

    # 2. 自动检测（DDGLite 始终可用，所以这里一定会返回）
    for p in _get_all_providers():
        if p.is_available():
            logger.info("Web search backend: %s (auto-detected)", p.name)
            return p


# ════════════════════════════════════════════════════════════
# 搜索结果格式化（供 LLM 使用的文本版）
# ════════════════════════════════════════════════════════════


def _format_search_results(data: Dict[str, Any], max_results: int) -> str:
    """将 Hermes 格式的搜索结果转为 LLM 友好的文本"""
    if not data.get("success"):
        return f"搜索失败: {data.get('error', '未知错误')}"

    web = data.get("data", {}).get("web", [])
    if not web:
        return "未找到结果"

    lines = []
    for i, r in enumerate(web[:max_results], 1):
        title = r.get("title", "").strip() or "(无标题)"
        snippet = r.get("description", "").strip() or ""
        url = r.get("url", "")
        if snippet:
            lines.append(f"{i}. {title} — {snippet}")
        else:
            lines.append(f"{i}. {title}")
        if url:
            lines[-1] += f"\n   {url}"

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# 主搜索函数（替换旧的 _web_search_fn）
# ════════════════════════════════════════════════════════════


def _web_search_fn(query: str, max_results: int = _DEFAULT_MAX_RESULTS) -> str:
    """搜索互联网，返回摘要列表。

    自动选择可用后端，统一结果格式。
    """
    if not query or not isinstance(query, str):
        return "错误: query 不能为空"

    provider = _get_search_backend()
    data = provider.search(query, max_results)
    return _format_search_results(data, max_results)


# ════════════════════════════════════════════════════════════
# ToolDef 定义
# ════════════════════════════════════════════════════════════

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
    logger.warning("[web_search_tools] ToolDef import failed: %s", e)
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


def get_search_provider_info() -> dict:
    """返回当前可用后端信息（供调试/管理接口使用）"""
    provider = _get_search_backend()
    return {
        "active_backend": provider.name,
        "available_backends": [
            {"name": p.name, "available": p.is_available()}
            for p in _get_all_providers()
        ],
    }
