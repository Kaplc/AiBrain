"""
Wiki MCP Server - 基于 LightRAG 的本地 Wiki 知识库工具
改为 HTTP 调用后端 Flask API，不再直接 import RAG 模块
提供 wiki_search / wiki_list / wiki_index 三个工具

日志标记规范：
  [MCP→]  MCP 层发出的请求
  [MCP←]  MCP 层收到的响应
  [MCP⚠]  MCP 层警告/降级
  [MCP✗]  MCP 层错误
"""
import os
import logging
import json
import urllib.request
import urllib.error
import time as _time

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("AiBrain Wiki Server")

# 后端 API 地址：优先从环境变量读取，否则从 .port_config 读取，最后默认 18765
_flask_port = os.environ.get('FLASK_PORT')
if not _flask_port:
    _port_config = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.port_config'))
    if os.path.exists(_port_config):
        try:
            with open(_port_config, 'r') as f:
                _flask_port = f.read().strip().split(',')[0]
        except Exception:
            pass

_backend_port = _flask_port or '18765'
_BACKEND_URL = os.environ.get("AIBRAIN_BACKEND_URL", f"http://127.0.0.1:{_backend_port}")
logger.info(f"[MCP] Wiki MCP Server 启动，后端地址: {_BACKEND_URL}")


def _api_call(path: str, data: dict | None = None, method: str = "POST") -> dict:
    """调用后端 API，带完整流程日志"""
    url = f"{_BACKEND_URL}{path}"
    body = json.dumps(data or {}).encode("utf-8") if data else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    t0 = _time.time()
    logger.info(f"[MCP→] HTTP {method} {path} | body_keys={list(data.keys()) if data else []}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = _time.time() - t0
            result = json.loads(raw)
            logger.info(
                f"[MCP←] HTTP {resp.status} {path} | "
                f"耗时={elapsed:.1f}s | "
                f"resp_keys={list(result.keys())}"
            )
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.read() else str(e)
        logger.error(f"[MCP✗] HTTP {e.code} {path} | body={err_body[:200]}")
        return {"error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        logger.error(f"[MCP✗] {path} 异常: {e}")
        return {"error": str(e)}


@mcp.tool()
def wiki_search(query: str, mode: str = "naive") -> str:
    """Search the wiki knowledge base.

    Args:
        query: The search question.
        mode: Query mode - naive/local/global/hybrid/mix (default: naive).
              naive=pure vector similarity (fast 0.2s, no LLM needed, **recommended default**),
              hybrid=LLM keyword extraction + knowledge graph + vector (best quality but slow ~30-60s),
              local/global/mix=knowledge graph enhanced modes (require LLM).
    """
    t0 = _time.time()
    logger.info(f"[MCP→] wiki_search 调用开始 query={query[:50]} mode={mode}")
    resp = _api_call("/wiki/search", {"query": query, "mode": mode})
    if "error" in resp:
        logger.error(f"[MCP✗] wiki_search 后端返回错误: {resp['error']}")
        return f"搜索出错: {resp['error']}"
    result = resp.get("result", "")
    used_mode = resp.get("mode", mode)
    elapsed_backend = resp.get("elapsed", 0)
    total = _time.time() - t0
    logger.info(
        f"[MCP←] wiki_search 完成 | "
        f"backend_mode={used_mode} backend_elapsed={elapsed_backend}s "
        f"mcp_total={total:.1f}s result_len={len(result) if result else 0}"
    )
    if not result or not result.strip():
        return "未找到相关内容。请尝试换个关键词或使用 wiki_index 重建索引。"
    return f"[模式: {used_mode}, 后端耗时: {elapsed_backend}s, MCP总耗时: {total:.1f}s]\n\n{result}"


@mcp.tool()
def wiki_list() -> list[dict]:
    """List all .md files in the wiki directory with basic info (name, size, last modified)."""
    t0 = _time.time()
    logger.info("[MCP→] wiki_list 调用开始")
    resp = _api_call("/wiki/list", method="GET")
    total = _time.time() - t0
    if "error" in resp:
        logger.error(f"[MCP✗] wiki_list 后端返回错误: {resp['error']}")
        return []
    files = resp.get("files", [])
    logger.info(f"[MCP←] wiki_list 完成 | mcp_total={total:.1f}s files_count={len(files)}")
    return files


@mcp.tool()
def wiki_index() -> str:
    """Manually trigger a full re-index of all .md files in the wiki directory.
    Use this after bulk changes or when search results seem stale.
    """
    t0 = _time.time()
    logger.info("[MCP→] wiki_index 调用开始")
    resp = _api_call("/wiki/index", {})
    total = _time.time() - t0
    if "error" in resp:
        logger.error(f"[MCP✗] wiki_index 后端返回错误: {resp['error']}")
        return f"索引出错: {resp['error']}"
    logger.info(f"[MCP←] wiki_index 完成 | mcp_total={total:.1f}s")
    parts = []
    if resp.get("added"):
        parts.append(f"新增索引: {', '.join(resp['added'])}")
    if resp.get("updated"):
        parts.append(f"更新索引: {', '.join(resp['updated'])}")
    if resp.get("deleted"):
        parts.append(f"移除索引: {', '.join(resp['deleted'])}")
    if resp.get("unchanged"):
        parts.append(f"未变: {resp['unchanged']} 个文件")
    if resp.get("errors"):
        parts.append(f"错误: {'; '.join(resp['errors'])}")
    if not parts:
        return "wiki 目录为空，无文件可索引。"
    return "\n".join(parts)


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("AiBrain WikiMCP")
    except Exception:
        pass
    mcp.run()
