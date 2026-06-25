"""记忆模块 - 统一导出入口

将 core.py 的公开函数统一导出，
外部 `from main_brain.memory import store_memory` 等调用保持不变。
"""

# mem0 兼容存根（旧代码仍 import get_mem0_client 时不会崩溃）
def get_mem0_client():
    """mem0 已移除，返回 Qdrant 客户端"""
    from modules.qdrant.store import get_qdrant_client
    return get_qdrant_client()

from .core import (
    # 设置
    get_memory_settings,
    update_memory_settings,
    # 客户端/计数
    warmup_memory_count,
    get_client,
    get_memory_count,
    # 存取
    store_memory,
    search_memory,
    list_memories,
    delete_memory,
    update_memory,
    # 整理
    organize_memories,
    dedup_memories,
    refine_memories,
    apply_organize,
    # 常量
    DEFAULT_USER_ID,
)

__all__ = [
    "get_memory_settings", "update_memory_settings",
    "warmup_memory_count", "get_client", "get_memory_count",
    "store_memory", "search_memory", "list_memories",
    "delete_memory", "update_memory",
    "organize_memories", "dedup_memories", "refine_memories", "apply_organize",
    "DEFAULT_USER_ID",
]
