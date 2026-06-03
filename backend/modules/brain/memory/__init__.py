"""记忆模块 - 统一导出入口

将 memory.py (现为 core.py) 的公开函数和 events 子模块统一导出，
外部 `from modules.brain.memory import store_memory` 等调用保持不变。
"""
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

from .events import get_event_store

__all__ = [
    "get_memory_settings", "update_memory_settings",
    "warmup_memory_count", "get_client", "get_memory_count",
    "store_memory", "search_memory", "list_memories",
    "delete_memory", "update_memory",
    "organize_memories", "dedup_memories", "refine_memories", "apply_organize",
    "DEFAULT_USER_ID",
    "get_event_store",
]
