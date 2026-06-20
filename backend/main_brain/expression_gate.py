"""ExpressionGate — 主动联系闸门（T010）

plan 第七节「主动联系用户闸门」7 个条件落到代码：
  value_score / interruption_risk / repetition_score / cooldown_ok + 安全策略。
输出 send / hold / suppress（plan ExpressionGateResult）。

定位：高层策略闸门。它判断「是否值得、是否打扰、是否冷却、是否重复」；
真正的 pick+生成+发送仍走现有 pending.proactive_send（低层执行，含 refractory），
二者互补不重复。
"""
from __future__ import annotations

import logging

from .config import get_brain_config
from .contracts import ExpressionGateResult, GATE_SEND, GATE_HOLD, GATE_SUPPRESS

logger = logging.getLogger("main_brain.gate")


class ExpressionGate:
    """主动表达闸门。无状态，纯函数式评估。"""

    def evaluate(
        self,
        candidate: dict,
        life_state: dict,
        *,
        recent_messages: list[dict] | None = None,
        chat_busy: bool = False,
    ) -> ExpressionGateResult:
        """评估一个主动表达候选。

        Args:
            candidate: {value, topic/content, source_node_id, ...}
            life_state: LifeState 快照（取 idle_seconds / last_proactive_contact_at）
            recent_messages: 最近系统回复/主动消息（算重复度）
            chat_busy: 用户是否正在 SSE 聊天（busy 时 interruption_risk 拉满）
        """
        cfg = get_brain_config()
        value_thr = float(cfg.get("proactive_value_threshold", 0.65))
        inter_max = float(cfg.get("proactive_interruption_max", 0.35))
        rep_max = float(cfg.get("proactive_repetition_max", 0.6))
        cooldown_min = float(cfg.get("proactive_cooldown_minutes", 30))

        value = self._value_score(candidate)
        interruption = self._interruption_risk(life_state, chat_busy)
        repetition = self._repetition_score(candidate, recent_messages)
        cooldown_ok = self._cooldown_ok(life_state, cooldown_min)

        # 安全策略：proactive 总开关关 → 直接 suppress
        if not cfg.proactive_enabled:
            return ExpressionGateResult(
                allowed=False, action=GATE_SUPPRESS, value_score=value,
                interruption_risk=interruption, repetition_score=repetition,
                cooldown_ok=cooldown_ok, reason="proactive_contact_enabled=False",
            )

        allowed = (
            value >= value_thr
            and interruption <= inter_max
            and repetition <= rep_max
            and cooldown_ok
        )

        if allowed:
            action, reason = GATE_SEND, self._send_reason(value, interruption, candidate)
        elif value >= value_thr * 0.8 or not cooldown_ok or interruption > inter_max:
            # 有价值但暂不满足 → 留在队列等下次
            action = GATE_HOLD
            reason = self._hold_reason(value, interruption, repetition, cooldown_ok)
        else:
            action, reason = GATE_SUPPRESS, "价值不足，降权丢弃"

        logger.info(
            f"[gate] {action} value={value:.2f} inter={interruption:.2f} "
            f"rep={repetition:.2f} cooldown_ok={cooldown_ok} | {reason}"
        )
        return ExpressionGateResult(
            allowed=allowed, action=action, value_score=value,
            interruption_risk=interruption, repetition_score=repetition,
            cooldown_ok=cooldown_ok, reason=reason,
        )

    # ── 分项 ─────────────────────────────────────────────────
    @staticmethod
    def _value_score(candidate: dict) -> float:
        """表达价值：优先用候选自带 value，否则回退 expression_score。"""
        v = candidate.get("value")
        if v is None:
            v = candidate.get("expression_score", 0.0)
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _interruption_risk(life_state: dict, chat_busy: bool) -> float:
        """打扰风险：正在聊天→1.0；否则随空闲秒数递减（刚互动最不该打扰）。"""
        if chat_busy:
            return 1.0
        idle = float(life_state.get("idle_seconds", 0) or 0)
        # 0s→0.9，到 30min(1800s)→~0.1
        risk = max(0.05, 0.9 * (1.0 - min(1.0, idle / 1800.0)))
        # 刚主动联系过不久也提高风险（避免连发）
        last = life_state.get("last_proactive_contact_at", "")
        mins_since = _minutes_since(last)
        if mins_since is not None and mins_since < 60:
            risk = max(risk, 0.6)
        return min(1.0, risk)

    @staticmethod
    def _repetition_score(candidate: dict, recent_messages: list[dict] | None) -> float:
        """与最近已表达内容的重复度（Jaccard on 字符 bigram，粗略）。"""
        if not recent_messages:
            return 0.0
        text = (candidate.get("topic") or candidate.get("content")
                or candidate.get("reason") or "")
        if not text:
            return 0.0
        cand_bigrams = _bigrams(text)
        if not cand_bigrams:
            return 0.0
        best = 0.0
        for m in recent_messages[-6:]:
            mt = ""
            if isinstance(m, dict):
                mt = m.get("content") or m.get("assistant") or m.get("text") or ""
            if not mt:
                continue
            mb = _bigrams(str(mt))
            if not mb:
                continue
            inter = len(cand_bigrams & mb)
            union = len(cand_bigrams | mb) or 1
            best = max(best, inter / union)
        return best

    @staticmethod
    def _cooldown_ok(life_state: dict, cooldown_min: float) -> bool:
        last = life_state.get("last_proactive_contact_at", "")
        if not last:
            return True
        mins = _minutes_since(last)
        return (mins is None) or (mins >= cooldown_min)

    @staticmethod
    def _send_reason(value, interruption, candidate):
        topic = candidate.get("topic") or candidate.get("source_node_id") or ""
        return f"价值 {value:.2f} 充足、打扰低 {interruption:.2f}，发送" + (
            f"（{topic[:20]}）" if topic else "")

    @staticmethod
    def _hold_reason(value, interruption, repetition, cooldown_ok):
        if not cooldown_ok:
            return "冷却未到，保留待下次"
        if interruption > 0.35:
            return f"打扰风险略高({interruption:.2f})，先保留 pending"
        if repetition > 0.6:
            return f"与最近表达重复({repetition:.2f})，先保留"
        return f"价值 {value:.2f} 偏低，保留观察"


def _bigrams(text: str) -> set[str]:
    t = text.replace(" ", "").replace("\n", "")
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def _minutes_since(iso_ts: str) -> float | None:
    """距 iso_ts 的分钟数；坏/空时间戳返回 None。"""
    if not iso_ts:
        return None
    try:
        import datetime as _dt
        dt = _dt.datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return (_dt.datetime.now(_dt.timezone.utc) - dt).total_seconds() / 60.0
    except Exception:
        return None


_gate: ExpressionGate | None = None


def get_expression_gate() -> ExpressionGate:
    global _gate
    if _gate is None:
        _gate = ExpressionGate()
    return _gate
