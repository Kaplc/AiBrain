"""assertions — schema 与状态断言（供 harness / 测试脚本复用）。"""
from __future__ import annotations

from ..contracts import ACTIONS, BrainCycle


def assert_decision_schema(d: dict) -> tuple[bool, str]:
    """校验 judge 原始 dict 是否符合 BrainJudgeDecision schema。
    Returns: (ok, message)。
    """
    if not isinstance(d, dict):
        return False, "not a dict"
    action = d.get("next_action")
    if action not in ACTIONS:
        return False, f"next_action {action!r} not in {ACTIONS}"
    if "thought_summary" not in d:
        return False, "missing thought_summary"
    conf = d.get("confidence", 0.5)
    try:
        if not (0.0 <= float(conf) <= 1.0):
            return False, f"confidence {conf} out of [0,1]"
    except (TypeError, ValueError):
        return False, f"confidence {conf!r} not numeric"
    return True, "ok"


def cycle_has_error(cycle: BrainCycle) -> bool:
    return bool(getattr(cycle, "error", ""))


def cycles_routed_correctly(cycles: list[BrainCycle]) -> tuple[bool, str]:
    """每个非终止 cycle 都应有 handler 执行结果或显式 error（不应静默丢失）。"""
    for c in cycles:
        if c.action in ("final_reply", "sleep", "abort"):
            continue
        if not c.action:
            return False, f"cycle {c.cycle_index} has empty action"
    return True, "ok"
