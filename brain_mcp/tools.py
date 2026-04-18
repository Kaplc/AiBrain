"""
MCP Tools - 通过 Flask API 调用，不直接加载模型或连接 Qdrant
只暴露 search 和 store 两个工具
"""
import os
import urllib.request
import urllib.error
import json

# 从环境变量或 .port_config 读取 Flask 端口
_flask_port = os.environ.get('FLASK_PORT')
if not _flask_port:
    _port_config = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.port_config'))
    if os.path.exists(_port_config):
        try:
            with open(_port_config, 'r') as f:
                _flask_port = f.read().strip().split(',')[0]
        except Exception:
            pass

API_BASE = f"http://127.0.0.1:{_flask_port or '18765'}"


def _call(path: str, data: dict) -> dict:
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
        raise RuntimeError(f"Memory服务未启动: {e}")


def store_memory(text: str, hit_ids: list = None) -> str:
    """存储新记忆，同时触发 hit_ids 中记忆的 hit_count++"""
    result = _call("/store", {"text": text, "hit_ids": hit_ids or []})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("result", "已记住")


def search_memory(query: str) -> list[dict]:
    """搜索记忆，只返回 id 和 text"""
    result = _call("/search", {"query": query})
    if "error" in result:
        raise RuntimeError(result["error"])
    return [{"id": r["id"], "text": r["text"]} for r in result.get("results", [])]


def update_memory(memory_id: str, new_text: str) -> str:
    """更新指定记忆的内容（同步）"""
    result = _call("/update", {"memory_id": memory_id, "new_text": new_text})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("result", "已更新")


def update_memory_async(memory_id: str, new_text: str) -> str:
    """更新指定记忆的内容（异步，后台执行）"""
    result = _call("/update-async", {"memory_id": memory_id, "new_text": new_text})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("result", "更新已提交后台")
