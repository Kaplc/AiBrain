"""mem0 兼容适配器（已废弃）—— 保留文件避免旧代码 import 崩溃

所有函数重定向到新的 Qdrant 存储层。
"""
from modules.brain.memory import get_mem0_client, get_client
from modules.brain.memory.qdrant_store import get_qdrant_client


def load_mem0_config():
    """读取 LLM 配置（原 mem0 配置）"""
    import json, os
    path = os.path.expanduser("~/.aibrain/config/mem0.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


__all__ = ["get_mem0_client", "get_client", "load_mem0_config", "get_qdrant_client"]
