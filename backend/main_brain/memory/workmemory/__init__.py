"""
WorkMemory 工作记忆模块

外部访问：
    from main_brain.memory.workmemory import get_work_memory, get_base_dir
    wm = get_work_memory()
"""
from .workmemory import WorkMemoryManager, get_work_memory, get_base_dir

__all__ = [
    "WorkMemoryManager",
    "get_work_memory",
    "get_base_dir",
]
