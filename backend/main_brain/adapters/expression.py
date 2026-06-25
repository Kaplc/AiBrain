"""Expression Adapter（T008 / T021）— 复用现有 pending_expression + expression_history。

create_pending 动作：把 judge 的 pending_intent 落进现有 pending 队列（复用去重/cap/
refractory）。发送走现有 proactive_send（低层 pick+生成+refractory），由 ExpressionGate
（T010）做高层 send/hold/suppress 判定。adapter 只编排，不重写冷却/重复逻辑。
"""
from __future__ import annotations

import logging

from ..contracts import (
    BrainJudgeDecision, BrainRunContext, GATE_SEND, GATE_HOLD, GATE_SUPPRESS,
)
from ..expression_gate import get_expression_gate

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

    # ── 评估 + 发送（gate → 现有 proactive_send）──────────
    def evaluate_and_send(
        self,
        life_state: dict,
        *,
        chat_busy: bool = False,
        recent_messages: list[dict] | None = None,
    ) -> dict:
        """评估队列里最佳 pending，按 gate 决定 send/hold/suppress。

        Returns: {gate, sent, content, reason}
        """
        gate = get_expression_gate()
        recent_messages = recent_messages if recent_messages is not None else self._recent_assistant()

        # 取最佳候选（绕过冷却拿最高分，给 gate 统一判定）
        try:
            best = self._pending()._pick_unexpressed_top()
        except Exception as e:
            logger.warning(f"[expr_adapter] pick failed: {e}")
            best = None

        if best is None:
            return {
                "gate": {"action": "hold", "allowed": False, "reason": "no pending"},
                "sent": False, "content": None, "reason": "no pending to send",
            }

        candidate = {
            "value": best.get("expression_score", 0.0),
            "topic": best.get("source_node_id", ""),
            "source_node_id": best.get("source_node_id", ""),
            "source": best.get("source", ""),
        }
        result = gate.evaluate(candidate, life_state,
                               recent_messages=recent_messages, chat_busy=chat_busy)

        sent_content = None
        if result.action == GATE_SEND:
            try:
                sent_content = self._pending().proactive_send()
                flushed = self._pending().flush_proactive_buffer()
                # 更新 last_proactive_contact_at
                from .state import get_state_adapter
                get_state_adapter().mark_proactive_contact()
                logger.info(
                    f"[expr_adapter] sent: content={bool(sent_content)} flushed={flushed}"
                )
            except Exception as e:
                logger.warning(f"[expr_adapter] proactive_send failed: {e}")
                result.reason = f"send error: {e}"

        return {
            "gate": result.to_dict(),
            "sent": bool(sent_content),
            "content": (sent_content or "")[:120],
            "reason": result.reason,
            "candidate": candidate,
        }

    def _recent_assistant(self, limit: int = 8) -> list[dict]:
        """读最近系统回复/主动消息（重复度判定用）。"""
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            out = []
            for e in entries[-limit:]:
                if e.get("assistant"):
                    out.append({"content": str(e["assistant"])[:200]})
            return out
        except Exception:
            return []

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
