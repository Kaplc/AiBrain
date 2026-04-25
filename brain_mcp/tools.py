"""
MCP Tools - 只暴露 store 和 search 两个工具
搜索参数由后端根据数据量自动适配，MCP 零配置
"""
import os
import urllib.request
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def store_memory(text: str) -> str:
    """存储记忆（LLM 自动拆分事实），返回实际记住的文本"""
    result = _call("/store", {"text": text})
    if "error" in result:
        raise RuntimeError(result["error"])
    texts = result.get("stored_texts", [])
    if texts:
        return f"已记住:\n" + "\n".join(f"  • {t}" for t in texts)
    # stored_texts为空时返回原始输入文本
    return f"已记住:\n  • {text}"


def search_memory(query: str) -> list[dict]:
    """搜索记忆（后端自动根据数据量选择最优策略），返回匹配的文本和分数"""
    result = _call("/memory/search", {"query": query})
    if "error" in result:
        raise RuntimeError(result["error"])
    return [{"text": r["text"], "score": r.get("score", 0)} for r in result.get("results", [])]
