"""Memory Adapter（T006）— 包装现有记忆检索，不复制记忆系统。

recall_memory 动作：用 judge 给的 query 走 modules.brain.memory.core.search_memory，
返回精简摘要喂回 context。失败降级返回空，绝不抛穿主流程。
"""
from __future__ import annotations

import logging

from ..contracts import BrainJudgeDecision, BrainRunContext

logger = logging.getLogger("main_brain.adapter.memory")


class MemoryAdapter:
    """记忆检索 adapter（只读）。"""

    def recall(self, query: str, top_k: int = 6) -> list[dict]:
        """检索长期记忆，返回 [{id, text, score}, ...] 精简列表。"""
        if not query or not query.strip():
            return []
        try:
            from main_brain.memory.core import search_memory
            hits = search_memory(query)
        except Exception as e:
            logger.warning(f"[mem_adapter] recall failed for {query!r}: {e}")
            return []
        out = []
        for h in hits[:top_k]:
            text = h.get("text", "") or h.get("memory", "")
            out.append({
                "id": h.get("id", ""),
                "text": text,
                "score": float(h.get("score", 0.0)),
            })
        if out:
            preview = " | ".join(f"[{h['score']:.2f}] {h['text'][:80]}" for h in out)
            logger.info(f"[mem_adapter] recall {query!r} -> {len(out)} hits: {preview[:200]}")
        else:
            logger.info(f"[mem_adapter] recall {query!r} -> 0 hits")
        return out

    # ── action_handler 约定 ─────────────────────────────────
    def handle_recall(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                      dry_run: bool) -> dict:
        query = str((decision.action_args or {}).get("query", "")).strip()
        if dry_run:
            return {"result_summary": f"[dry_run] recall: {query[:60]}"}
        hits = self.recall(query)
        summary = f"召回 {len(hits)} 条记忆" + (
            f"，首条：{hits[0]['text'][:50]}" if hits else ""
        )
        return {"result_summary": summary, "memory_context": hits}


_memory_adapter: MemoryAdapter | None = None


def get_memory_adapter() -> MemoryAdapter:
    global _memory_adapter
    if _memory_adapter is None:
        _memory_adapter = MemoryAdapter()
    return _memory_adapter
