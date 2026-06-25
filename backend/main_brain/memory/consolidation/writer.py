"""长期记忆写入器（T007 / FR-003）

复用现有 store_memory() 写入 aibrain_memories。语义去重/合并不在此处理 ——
store 流水线的 episodic_merge（0.85）已覆盖；本层只负责：
  - 组装 LongTermMemoryPayload 元数据（来源 / 类型 / 重要性 / hash）
  - 调用 store_memory，解析 added/updated/deleted
  - 回填 memory_id 给候选

写入失败不抛穿（返回 error 结构），由 orchestrator 计入 error_count / trace。
"""
from __future__ import annotations

import logging

from .contracts import MemoryCandidate, LongTermMemoryPayload

logger = logging.getLogger("memory.consolidation.writer")


def write_candidate(candidate: MemoryCandidate, *, run_id: str = "") -> dict:
    """把一条候选写入长期记忆。

    Returns:
        {"ok": bool, "memory_id": str, "added": int, "deleted": int,
         "merged": bool, "error": str}
        merged=True 表示 store 流水线命中了已有相似记忆并合并（计入 updated）。
    """
    text = candidate.summary
    if not text:
        return {"ok": False, "memory_id": "", "added": 0, "deleted": 0,
                "merged": False, "error": "empty summary"}

    payload = LongTermMemoryPayload(
        source=candidate.source_type,
        source_seq=candidate.source_seq,
        source_run_id=run_id,
        memory_kind=candidate.memory_kind,
        importance=candidate.importance,
        tags=["consolidation", candidate.memory_kind],
        source_hash=candidate.source_hash,
    )
    try:
        from ..core import store_memory
        result = store_memory(text, memory_meta=payload.to_meta())
    except Exception as e:
        logger.warning(f"[writer] store_memory failed: {e}")
        return {"ok": False, "memory_id": "", "added": 0, "deleted": 0,
                "merged": False, "error": str(e)}

    added = int(result.get("added_count", 0) or 0)
    deleted = int(result.get("deleted_count", 0) or 0)
    stored = result.get("stored_texts", []) or []
    # memory_id：store 不直接返回 point id，用 stored_texts[0] 占位记录（可追溯文本）
    memory_id = str(stored[0]) if stored else ""

    return {
        "ok": True,
        "memory_id": memory_id,
        "added": added,
        "deleted": deleted,
        "merged": deleted > 0,   # pipeline 删了旧记忆即视为合并
        "error": "",
    }
