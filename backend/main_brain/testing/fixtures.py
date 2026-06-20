"""fixtures — 构造测试用 LifeState / BrainRunContext / 候选。"""
from __future__ import annotations

from ..contracts import (
    BrainRun, BrainRunContext, REACTIVE, BACKGROUND, TICK_MEDIUM,
    default_life_state,
)


def sample_life_state(**overrides) -> dict:
    """默认 LifeState，可覆盖部分字段。"""
    s = default_life_state()
    s.update(overrides)
    return s


def sample_candidate(**overrides) -> dict:
    """默认主动表达候选。"""
    base = {"value": 0.8, "topic": "记忆系统", "source_node_id": "记忆系统",
            "source": "concern", "reason": "想聊聊记忆"}
    base.update(overrides)
    return base


def build_life_test_context(
    *,
    mode: str = BACKGROUND,
    tick_type: str = TICK_MEDIUM,
    life_state: dict | None = None,
    trigger: dict | None = None,
    budgets: dict | None = None,
) -> BrainRunContext:
    """构造测试用 BrainRunContext，避免每个测试重复拼装。"""
    run = BrainRun(
        run_id="br_test_ctx",
        mode=mode,
        trigger=trigger or ({"user_message": "测试消息"} if mode == REACTIVE
                            else {"tick_type": tick_type}),
        started_at="2026-06-20T00:00:00+00:00",
    )
    ctx = BrainRunContext(
        run=run,
        life_state=life_state if life_state is not None else sample_life_state(),
        trigger=run.trigger,
        tick_type=tick_type,
        selected_activity="reflect",
        budgets=budgets or {},
    )
    return ctx
