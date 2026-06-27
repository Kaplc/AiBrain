"""ActivitySelector — 自主活动选择（T009 / FR-007 / FR-014 / FR-014-r2）

规则式（不调 LLM），给定 LifeState + tick_type 决定本轮做什么活动。确定性、可解释，
返回 (activity, reason, confidence)。ActivitySelector 与 Arbiter 分工：它定「候选」，
Arbiter 在低置信时仲裁（plan 关键决策 #3）。

confidence 含义：
  1.0-0.75  强信号，直接采纳
  0.75-0.55 中等匹配，可采纳
  <0.55     低置信，触发 Arbiter（前额叶）LLM 仲裁

autonomy_level=observe 时一律 wait（最低自主），其余按 tick 节奏推进。
"""
from __future__ import annotations

import logging

from .contracts import (
    TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY, TICK_MANUAL,
)
from .config import get_brain_config

logger = logging.getLogger("main_brain.activity")

# 各活动的基础置信度（规则式匹配的确定性程度）
_CONFIDENCE = {
    "proactive_contact": 0.85,
    "advance_open_loop": 0.75,
    "self_learn": 0.60,
    "review_learned": 0.55,
    "prepare_expression": 0.55,
    "reflect": 0.50,
    "organize_memory": 0.75,
    "maintain_goal": 0.80,
    "wait": 0.35,
}


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
    ) -> tuple[str, str, float]:
        """Returns: (activity, reason, confidence)。

        activity 来自 activities/*.md 文件定义（含 wait fallback）。
        confidence 0-1，低于 _CONFIDENCE 默认值的降级表明规则式不自信。
        """
        autonomy = (autonomy_level or "assist").lower()
        if autonomy == "observe":
            return ("wait", "autonomy=observe，仅观察不行动", 1.0)

        idle = float(life_state.get("idle_seconds", 0) or 0)
        pending = pending_expressions or life_state.get("pending_expressions", []) or []
        open_loops = life_state.get("open_loops", []) or []
        energy = float(life_state.get("energy", 0.6) or 0.6)

        if tick_type == TICK_SHORT:
            return ("wait", "short_tick 只做轻量检查，不调 LLM", 1.0)

        if tick_type == TICK_MEDIUM:
            return self._select_medium(life_state, idle, pending, open_loops, autonomy)

        if tick_type == TICK_LONG:
            return self._select_long(life_state, energy, autonomy)

        if tick_type == TICK_DAILY:
            return self._select_daily(life_state, autonomy)

        # manual / 未知
        return ("reflect", "manual/未知 tick，默认反思一次", 0.70)

    # ── 各 tick 策略 ─────────────────────────────────────────
    def _select_medium(self, life_state, idle, pending, open_loops,
                       autonomy) -> tuple[str, str, float]:
        # 1. 主动联系（需总开关 + 充分空闲 + 有待表达）
        if (autonomy in ("assist", "autonomous", "high_autonomy")
                and idle > 600 and pending):
            return ("proactive_contact",
                    f"空闲 {idle:.0f}s 且有 {len(pending)} 条待表达",
                    _CONFIDENCE["proactive_contact"])

        # 2. 推进未决问题（空闲够且存在 open loop）
        if idle > 180 and open_loops:
            top = open_loops[0] if isinstance(open_loops[0], dict) else {"content": str(open_loops[0])}
            conf = _CONFIDENCE["advance_open_loop"]
            # 如果有 pending 也同时满足，说明多条件冲突 → 降置信
            if pending:
                conf -= 0.15
            return ("advance_open_loop",
                    f"存在未决问题「{str(top.get('content',''))[:20]}」且空闲 {idle:.0f}s",
                    conf)

        # 2.5 自主学习（好奇心驱动 + 有缺口或目标）
        cfg = get_brain_config()
        if (cfg.get("self_learn_enabled", True)
                and idle > 180
                and (life_state.get("open_loops") or life_state.get("goals"))):
            drives = life_state.get("drives", {}) or {}
            curiosity = float(drives.get("curiosity", 0) or 0)
            threshold = float(cfg.get("self_learn_curiosity_threshold", 0.6))
            if curiosity >= threshold:
                return ("self_learn",
                        f"好奇心 {curiosity:.1f} + 空闲 {idle:.0f}s，适合主动学习",
                        _CONFIDENCE["self_learn"])

        # 2.6 复习已学知识（有空闲时回顾自学习内容）
        if (cfg.get("review_learned_enabled", True)
                and idle > 300):
            return ("review_learned",
                    f"空闲 {idle:.0f}s，适合复习已学知识",
                    _CONFIDENCE["review_learned"])

        # 3. 准备表达（有待表达但还不够空闲，先攒着）
        if pending and idle <= 600:
            return ("prepare_expression",
                    f"有 {len(pending)} 条待表达，先准备不急发",
                    _CONFIDENCE["prepare_expression"])

        # 4. 反思（近期想法少）
        thoughts = life_state.get("recent_thoughts", []) or []
        if len(thoughts) < 2:
            return ("reflect", "近期想法偏少，反思补充",
                    _CONFIDENCE["reflect"])

        return ("wait", "暂无值得推进的事，安静等待",
                _CONFIDENCE["wait"])

    def _select_long(self, life_state, energy, autonomy) -> tuple[str, str, float]:
        # 长 tick：整理记忆为主，精力低则只维护目标
        if energy < 0.3:
            return ("maintain_goal",
                    f"精力 {energy:.2f} 偏低，维护目标即可",
                    _CONFIDENCE["maintain_goal"])
        return ("organize_memory",
                "长 tick 整理近期记忆、去重、生成 lesson 候选",
                _CONFIDENCE["organize_memory"])

    def _select_daily(self, life_state, autonomy) -> tuple[str, str, float]:
        # 日 tick：先反思，再维护目标
        return ("reflect", "日 tick 执行每日反思", 0.90)


_selector: ActivitySelector | None = None


def get_activity_selector() -> ActivitySelector:
    global _selector
    if _selector is None:
        _selector = ActivitySelector()
    return _selector


def is_valid_activity(activity: str) -> bool:
    """检查是否为已注册活动（优先用 registry，fallback 到 contracts fallback）。"""
    try:
        from .activities.registry import get_activity
        return get_activity(activity) is not None
    except Exception:
        return activity in _ACTIVITIES_FALLBACK


# 内联 fallback 避免循环 import
_ACTIVITIES_FALLBACK = (
    "wait", "reflect", "organize_memory", "advance_open_loop",
    "maintain_goal", "prepare_expression", "proactive_contact",
    "self_learn", "review_learned", "use_tool",
)
