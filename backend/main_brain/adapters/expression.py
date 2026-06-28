"""Expression Adapter（T008 / T021）— 复用现有 pending_expression + expression_history。

create_pending 动作：把 judge 的 pending_intent 落进现有 pending 队列（复用去重/cap/
refractory）。发送走现有 proactive_send（低层 pick+生成+refractory），由 ExpressionGate
（T010）做高层 send/hold/suppress 判定。adapter 只编排，不重写冷却/重复逻辑。
"""
from __future__ import annotations

import logging

from ..contracts import BrainJudgeDecision, BrainRunContext

logger = logging.getLogger("main_brain.adapter.expression")


class ExpressionAdapter:
    """主动表达 adapter（包装 pending / expression_history / gate）。"""

    def _pending(self):
        from main_brain.state import get_pending
        return get_pending()

    # ── 创建 pending（judge 意图 → 现有队列）──────────────
    def create_pending_from_intent(self, intent: dict) -> dict | None:
        """把 judge 的 pending_intent 转成现有 pending entry。

        intent: {reason, value, topic}
        映射：source_node_id=topic, expression_score=value, type/source 固定。
        复用 PendingExpressionManager._create 的去重 + cap 逻辑。
        """
        intent = intent or {}
        topic = str(intent.get("topic") or intent.get("source_node_id") or "general").strip()
        try:
            value = float(intent.get("value", 0.0))
        except (TypeError, ValueError):
            value = 0.0
        if not topic or value <= 0:
            return None
        note = str(intent.get("reason", "") or intent.get("content", ""))[:300]
        try:
            created = self._pending()._create(
                type_="judge_pending",
                source_node_id=topic,
                expression_score=value,
                source="brain_judge",
                note=note,
            )
            return {"topic": topic, "value": value, "note": note[:80], "created": created}
        except Exception as e:
            logger.warning(f"[expr_adapter] create_pending failed: {e}")
            return None

    # ── action_handler 约定 ─────────────────────────────────
    def handle_create_pending(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                              dry_run: bool) -> dict:
        intent = decision.pending_expression or {}
        if dry_run:
            return {"result_summary": f"[dry_run] create_pending: {intent.get('topic','')}"}
        res = self.create_pending_from_intent(intent)
        if res is None:
            return {"result_summary": "create_pending: 无有效意图"}
        return {
            "result_summary": f"建 pending({res['topic'][:20]}, v={res['value']:.2f})",
            "pending_created": [res],
            "notify_candidate": res if decision.should_notify_user else {},
        }


_expression_adapter: ExpressionAdapter | None = None


def get_expression_adapter() -> ExpressionAdapter:
    global _expression_adapter
    if _expression_adapter is None:
        _expression_adapter = ExpressionAdapter()
    return _expression_adapter
