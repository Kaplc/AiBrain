"""Learning Adapter（T017）— 后台学习沉淀，不阻塞回复。

把 judge 的 learning_hints / thought_summary 沉淀为：
  1. life.recent_thoughts（短摘要，调试用）；
  2. （可选）self_narrative 的 cycle summary —— 若 self_narrative 可用则尝试更新，
     不可用则静默降级。

handle_final_reply 同时负责把 judge 的 reply_strategy 落到 run.final_strategy，
供最终回复环节使用。
"""
from __future__ import annotations

import logging

from ..contracts import BrainJudgeDecision, BrainRunContext

logger = logging.getLogger("main_brain.adapter.learning")


class LearningAdapter:
    """学习沉淀 adapter。"""

    def __init__(self):
        from .state import get_state_adapter
        self._state = get_state_adapter()

    def sink_hints(self, hints: list[str], *, thought: str = "", focus: str = "",
                   source: str = "background") -> None:
        """把 learning_hints / thought 摘要写进 life.recent_thoughts。"""
        parts = [h for h in (hints or []) if h]
        if thought:
            parts.insert(0, thought)
        for p in parts:
            self._state.append_recent_thought(p[:200], focus=focus, source=source)

    def try_self_narrative_update(self, thought: str, focus: str = "") -> None:
        """best-effort 更新 self narrative（不可用则降级）。"""
        if not thought:
            return
        try:
            from modules.brain.memory.self_narrative import get_self_narrative
            sn = get_self_narrative()
            if sn:
                # v1：仅作为一次反思记录写入，具体方法由 self_narrative 决定
                reflect = getattr(sn, "record_reflection", None)
                if callable(reflect):
                    reflect(thought, focus=focus)
        except Exception as e:
            logger.debug(f"[learn_adapter] self_narrative update skipped: {e}")

    # ── action_handler 约定 ─────────────────────────────────
    def handle_final_reply(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                           dry_run: bool) -> dict:
        """reactive 终止：落 reply_strategy（learning_hints 由 caller 统一沉淀）。"""
        ctx.run.final_strategy = decision.reply_strategy or {}
        keys = list((decision.reply_strategy or {}).keys())
        return {"result_summary": f"回复策略: {keys}"}


_learning_adapter: LearningAdapter | None = None


def get_learning_adapter() -> LearningAdapter:
    global _learning_adapter
    if _learning_adapter is None:
        _learning_adapter = LearningAdapter()
    return _learning_adapter
