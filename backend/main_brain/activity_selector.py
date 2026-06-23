"""ActivitySelector — 自主活动选择（T009 / FR-007 / FR-014）

规则式（不调 LLM），给定 LifeState + tick_type 决定本轮做什么活动。确定性、可解释，
返回 (activity, reason)。ActivitySelector 与 BrainJudge 分工：它定「做什么」，
judge 定「这件事下一步怎么做」（plan 关键决策 #3）。

autonomy_level=observe 时一律 wait（最低自主），其余按 tick 节奏推进。
"""
from __future__ import annotations

import logging

from .contracts import (
    ACTIVITIES, TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY, TICK_MANUAL,
)

logger = logging.getLogger("main_brain.activity")


class ActivitySelector:
    """规则式自主活动选择器。无状态。"""

    def select(
        self,
        life_state: dict,
        tick_type: str = TICK_MEDIUM,
        *,
        recent_runs: list[dict] | None = None,
        pending_expressions: list[dict] | None = None,
        autonomy_level: str = "assist",
    ) -> tuple[str, str]:
        """Returns: (activity, reason)。

        activity ∈ ACTIVITIES（含 wait）。
        """
        autonomy = (autonomy_level or "assist").lower()
        if autonomy == "observe":
            return ("wait", "autonomy=observe，仅观察不行动")

        idle = float(life_state.get("idle_seconds", 0) or 0)
        pending = pending_expressions or life_state.get("pending_expressions", []) or []
        open_loops = life_state.get("open_loops", []) or []
        energy = float(life_state.get("energy", 0.6) or 0.6)

        if tick_type == TICK_SHORT:
            return ("wait", "short_tick 只做轻量检查，不调 LLM")

        if tick_type == TICK_MEDIUM:
            return self._select_medium(life_state, idle, pending, open_loops, autonomy)

        if tick_type == TICK_LONG:
            return self._select_long(life_state, energy, autonomy)

        if tick_type == TICK_DAILY:
            return self._select_daily(life_state, autonomy)

        # manual / 未知
        return ("reflect", "manual/未知 tick，默认反思一次")

    # ── 各 tick 策略 ─────────────────────────────────────────
    def _select_medium(self, life_state, idle, pending, open_loops, autonomy) -> tuple[str, str]:
        # 1. 主动联系（需总开关 + 充分空闲 + 有待表达）
        if (autonomy in ("assist", "autonomous", "high_autonomy")
                and idle > 600 and pending):
            return ("proactive_contact", f"空闲 {idle:.0f}s 且有 {len(pending)} 条待表达")

        # 2. 推进未决问题（空闲够且存在 open loop）
        if idle > 180 and open_loops:
            top = open_loops[0] if isinstance(open_loops[0], dict) else {"content": str(open_loops[0])}
            return ("advance_open_loop",
                    f"存在未决问题「{str(top.get('content',''))[:20]}」且空闲 {idle:.0f}s")

        # 3. 准备表达（有待表达但还不够空闲，先攒着）
        if pending and idle <= 600:
            return ("prepare_expression", f"有 {len(pending)} 条待表达，先准备不急发")

        # 4. 反思（近期想法少）
        thoughts = life_state.get("recent_thoughts", []) or []
        if len(thoughts) < 2:
            return ("reflect", "近期想法偏少，反思补充")

        return ("wait", "暂无值得推进的事，安静等待")

    def _select_long(self, life_state, energy, autonomy) -> tuple[str, str]:
        # 长 tick：整理记忆为主，精力低则只维护目标
        if energy < 0.3:
            return ("maintain_goal", f"精力 {energy:.2f} 偏低，维护目标即可")
        return ("organize_memory", "长 tick 整理近期记忆、去重、生成 lesson 候选")

    def _select_daily(self, life_state, autonomy) -> tuple[str, str]:
        # 日 tick：先反思，再维护目标
        return ("reflect", "日 tick 执行每日反思")


_selector: ActivitySelector | None = None


def get_activity_selector() -> ActivitySelector:
    global _selector
    if _selector is None:
        _selector = ActivitySelector()
    return _selector


def is_valid_activity(activity: str) -> bool:
    return activity in ACTIVITIES
