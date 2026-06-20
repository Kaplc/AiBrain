"""main_brain 数据契约（T001）

所有循环共用的数据结构（dataclass）。reactive session 与 background life tick
共享 BrainRunContext / BrainJudgeDecision / adapter 调用约定，故集中定义。

字段含义见 plan 第六节「数据结构」，这里用 dataclass 落地，并补充默认值与
构造工厂，避免调用方重复拼装。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── 枚举常量（字符串，便于日志/JSON 直接用）──────────────────
REACTIVE = "reactive"
BACKGROUND = "background"

TICK_SHORT = "short_tick"
TICK_MEDIUM = "medium_tick"
TICK_LONG = "long_tick"
TICK_DAILY = "daily_tick"
TICK_MANUAL = "manual_tick"

# BrainJudgeDecision.next_action 合法集合
ACTIONS = (
    "recall_memory",   # 检索长期/工作记忆
    "use_tool",        # 调用白名单工具
    "update_state",    # 写 focus / working set / open loops / goals
    "create_pending",  # 想说但暂不发送
    "final_reply",     # reactive 最终回复
    "sleep",           # 等待/观察/休眠
    "abort",           # 异常终止
)

# 自主活动类型（ActivitySelector 输出）
ACTIVITIES = (
    "wait", "reflect", "organize_memory", "advance_open_loop",
    "maintain_goal", "prepare_expression", "proactive_contact", "use_tool",
)

STOP_REASONS = ("ready", "sleep", "max_cycles", "error", "timeout", "fallback")

# ExpressionGate action
GATE_SEND = "send"
GATE_HOLD = "hold"
GATE_SUPPRESS = "suppress"

# autonomy 等级
AUTONOMY_LEVELS = ("observe", "assist", "autonomous", "high_autonomy")


def default_life_state() -> dict:
    """LifeState 最小 JSON 形态（plan 第六节）。落在 internal_state.json['life']。"""
    return {
        "life_loop_status": "idle_thinking",
        "current_activity": "wait",
        "current_focus": "",
        "focus_since": "",
        "last_activity_at": "",
        "last_user_contact_at": "",
        "idle_seconds": 0,
        "autonomy_level": "assist",
        "energy": 0.6,
        "mood": {"valence": 0.0, "arousal": 0.3, "label": "neutral"},
        "working_set": [],
        "open_loops": [],
        "goals": [],
        "recent_thoughts": [],
        "pending_expressions": [],
        "relationship_context": {},
        "self_narrative_summary": "",
        "last_proactive_contact_at": "",
        "next_wake_hint": {},
        "last_error": "",
    }


@dataclass
class BrainCycle:
    """单轮内部循环记录。"""
    cycle_index: int = 0
    thought_summary: str = ""
    focus: str = ""
    action: str = ""
    action_args: dict = field(default_factory=dict)
    result_summary: str = ""
    reply_ready: bool = False
    notify_candidate: dict = field(default_factory=dict)
    confidence: float = 0.0
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle_index": self.cycle_index,
            "thought_summary": self.thought_summary,
            "focus": self.focus,
            "action": self.action,
            "action_args": self.action_args,
            "result_summary": self.result_summary,
            "reply_ready": self.reply_ready,
            "notify_candidate": self.notify_candidate,
            "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
        }


@dataclass
class BrainRun:
    """一次循环运行基础信息。"""
    run_id: str = ""
    mode: str = REACTIVE          # reactive / background
    trigger: dict = field(default_factory=dict)
    started_at: str = ""
    cycles: list[BrainCycle] = field(default_factory=list)
    memory_context: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    state_deltas: list[dict] = field(default_factory=list)
    pending_created: list[dict] = field(default_factory=list)
    final_strategy: dict = field(default_factory=dict)
    stop_reason: str = ""
    finished_at: str = ""
    selected_activity: str = ""   # background 才有
    learning_hints: list[str] = field(default_factory=list)

    def to_summary(self) -> dict:
        """精简摘要（不含长文本/敏感数据），供 /chat/state、runs/recent。"""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cycle_count": len(self.cycles),
            "selected_activity": self.selected_activity,
            "actions": [c.action for c in self.cycles if c.action],
            "stop_reason": self.stop_reason,
            "last_error": self.cycles[-1].error if self.cycles else "",
        }

    def to_full(self) -> dict:
        """完整轨迹（调试用）。"""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "selected_activity": self.selected_activity,
            "cycles": [c.to_dict() for c in self.cycles],
            "memory_context_count": len(self.memory_context),
            "tool_results": self.tool_results,
            "state_deltas": self.state_deltas,
            "pending_created": self.pending_created,
            "final_strategy": self.final_strategy,
            "learning_hints": self.learning_hints,
            "stop_reason": self.stop_reason,
        }


@dataclass
class BrainRunContext:
    """reactive session 与 background tick 共用的运行上下文。

    负责把输入、状态、记忆、工具结果、中间循环结果合并给 ActivitySelector 与
    BrainJudge。runner 每个 cycle 更新它，judge 据此决策。
    """
    run: BrainRun
    life_state: dict
    trigger: dict = field(default_factory=dict)
    cycles: list[BrainCycle] = field(default_factory=list)
    memory_context: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    pending_expressions: list[dict] = field(default_factory=list)
    budgets: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    selected_activity: str = ""
    tick_type: str = ""

    def add_error(self, msg: str) -> None:
        if msg and msg not in self.errors:
            self.errors.append(msg)

    def to_judge_view(self) -> dict:
        """喂给 BrainJudge 的精简视图（避免把整个 context 丢进 prompt）。"""
        last = self.cycles[-1] if self.cycles else None
        return {
            "mode": self.run.mode,
            "tick_type": self.tick_type,
            "trigger": self.trigger,
            "selected_activity": self.selected_activity,
            "life_state": _slim_life_state(self.life_state),
            "cycles_done": len(self.cycles),
            "last_cycle": last.to_dict() if last else None,
            "memory_context": [
                {"text": (m.get("text", "") or m.get("memory", ""))[:160],
                 "score": m.get("score", 0.0)}
                for m in self.memory_context[:6]
            ],
            "tool_results": [
                {"name": t.get("name", ""), "summary": str(t.get("result", ""))[:160]}
                for t in self.tool_results[:4]
            ],
            "pending_count": len(self.pending_expressions),
            "errors": self.errors[-3:],
            "budgets": self.budgets,
        }


def _slim_life_state(life_state: dict) -> dict:
    """给 judge 看的 LifeState 精简视图（去掉大数组原文）。"""
    if not isinstance(life_state, dict):
        return {}
    return {
        "life_loop_status": life_state.get("life_loop_status", ""),
        "current_activity": life_state.get("current_activity", ""),
        "current_focus": life_state.get("current_focus", ""),
        "idle_seconds": life_state.get("idle_seconds", 0),
        "energy": life_state.get("energy", 0.0),
        "mood": life_state.get("mood", {}),
        "autonomy_level": life_state.get("autonomy_level", "assist"),
        "working_set": [w.get("ref_id", w) if isinstance(w, dict) else str(w)
                        for w in life_state.get("working_set", [])[:8]],
        "open_loops": [l.get("content", "") if isinstance(l, dict) else str(l)
                       for l in life_state.get("open_loops", [])[:5]],
        "goals": [g.get("name", "") if isinstance(g, dict) else str(g)
                  for g in life_state.get("goals", [])[:5]],
        "recent_thoughts": [t.get("summary", str(t)) if isinstance(t, dict) else str(t)
                            for t in life_state.get("recent_thoughts", [])[:4]],
    }


@dataclass
class BrainJudgeDecision:
    """BrainJudge 单轮结构化输出（对应 plan BrainJudgeDecision）。"""
    thought_summary: str = ""
    mode: str = REACTIVE
    focus: str = ""
    next_action: str = ""
    action_args: dict = field(default_factory=dict)
    state_updates: dict = field(default_factory=dict)
    pending_expression: dict = field(default_factory=dict)
    reply_strategy: dict = field(default_factory=dict)
    should_notify_user: bool = False
    notify_reason: str = ""
    learning_hints: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "BrainJudgeDecision":
        d = d or {}
        return cls(
            thought_summary=str(d.get("thought_summary", ""))[:500],
            mode=str(d.get("mode", REACTIVE)),
            focus=str(d.get("focus", ""))[:200],
            next_action=str(d.get("next_action", "")),
            action_args=_as_dict(d.get("action_args")),
            state_updates=_as_dict(d.get("state_updates")),
            pending_expression=_as_dict(d.get("pending_expression")),
            reply_strategy=_as_dict(d.get("reply_strategy")),
            should_notify_user=bool(d.get("should_notify_user", False)),
            notify_reason=str(d.get("notify_reason", ""))[:300],
            learning_hints=[str(x) for x in d.get("learning_hints", []) if x][:10],
            confidence=_clamp(float(d.get("confidence", 0.5))),
        )

    def to_dict(self) -> dict:
        return {
            "thought_summary": self.thought_summary,
            "mode": self.mode,
            "focus": self.focus,
            "next_action": self.next_action,
            "action_args": self.action_args,
            "state_updates": self.state_updates,
            "pending_expression": self.pending_expression,
            "reply_strategy": self.reply_strategy,
            "should_notify_user": self.should_notify_user,
            "notify_reason": self.notify_reason,
            "learning_hints": self.learning_hints,
            "confidence": self.confidence,
        }


@dataclass
class ExpressionGateResult:
    """主动表达闸门结果（plan ExpressionGateResult）。"""
    allowed: bool = False
    action: str = GATE_HOLD     # send / hold / suppress
    value_score: float = 0.0
    interruption_risk: float = 1.0
    repetition_score: float = 0.0
    cooldown_ok: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "value_score": round(self.value_score, 3),
            "interruption_risk": round(self.interruption_risk, 3),
            "repetition_score": round(self.repetition_score, 3),
            "cooldown_ok": self.cooldown_ok,
            "reason": self.reason,
        }


@dataclass
class TickInput:
    """每次 life tick 的固定输入（plan TickInput）。"""
    tick_id: str = ""
    tick_type: str = TICK_MEDIUM
    now: str = ""
    life_state: dict = field(default_factory=dict)
    recent_runs: list[dict] = field(default_factory=list)
    recent_user_messages: list[dict] = field(default_factory=list)
    recent_assistant_messages: list[dict] = field(default_factory=list)
    memory_digest: dict = field(default_factory=dict)
    pending_expressions: list[dict] = field(default_factory=list)
    tool_context: dict = field(default_factory=dict)
    budgets: dict = field(default_factory=dict)


@dataclass
class TickOutput:
    """每次 life tick 的固定输出（plan TickOutput）。"""
    run_id: str = ""
    selected_activity: str = ""
    thought_summary: str = ""
    state_delta: dict = field(default_factory=dict)
    memory_actions: list[dict] = field(default_factory=list)
    tool_actions: list[dict] = field(default_factory=list)
    pending_expression: dict = field(default_factory=dict)
    proactive_contact: dict = field(default_factory=dict)
    learning_hints: list[str] = field(default_factory=list)
    next_wake_hint: dict = field(default_factory=dict)
    stop_reason: str = ""


# ── 小工具 ───────────────────────────────────────────────────
def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))
