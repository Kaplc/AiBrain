"""输出记忆沉淀 — 统筹子包

提供完整的后台沉淀流水线（采集 → 预筛 → LLM 批量判断 → 去重 → 写入 → 轨迹）。
外部访问：
    from main_brain.consolidation import consolidate_memory, ...
"""
from .core import (
    build_consolidation_context,
    extract_memory_candidates,
    score_memory_candidate,
    consolidate_memory,
    preview_memory_consolidation,
    enqueue_consolidation,
    is_auto_trigger_enabled,
)
