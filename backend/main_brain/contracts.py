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
    procedure_matches: list[dict] = field(default_factory=list)
    pending_expressions: list[dict] = field(default_factory=list)
    budgets: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    tool_context: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    selected_activity: str = ""
    tick_type: str = ""

    def add_error(self, msg: str) -> None:
        if msg and msg not in self.errors:
            self.errors.append(msg)

    def to_judge_view(self) -> dict:
        """喂给 BrainJudge 的精简视图（避免把整个 context 丢进 prompt）。"""
        last = self.cycles[-1] if self.cycles else None
        matches = []
        for m in (self.procedure_matches or [])[:3]:
            if not isinstance(m, dict):
                continue
            matches.append({
                "template_id": str(m.get("template_id", "")),
                "score": round(float(m.get("score", 0.0) or 0.0), 3),
                "context_fit": round(float(m.get("context_fit", 0.0) or 0.0), 3),
                "success_fit": round(float(m.get("success_fit", 0.0) or 0.0), 3),
                "reason": str(m.get("reason", ""))[:180],
                "action_hint": str(m.get("action_hint", ""))[:120],
                "step_preview": [str(s)[:60] for s in (m.get("step_preview", []) or [])[:5]],
            })
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
            "procedure_matches": matches,
            "pending_count": len(self.pending_expressions),
            "errors": self.errors[-3:],
            "budgets": self.budgets,
            "tool_context": self.tool_context,
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


# ═══════════════════════════════════════════════════════════════
# 统一事件回路（T001 / FR-001）
# BrainEvent / BrainCycleContext — 统一所有输入输出形态
# ═══════════════════════════════════════════════════════════════

# 事件来源枚举
EVENT_SOURCE_CHAT = "chat"
EVENT_SOURCE_TOOL = "tool"
EVENT_SOURCE_TICK = "tick"
EVENT_SOURCE_REFLECTION = "reflection"
EVENT_SOURCE_SYSTEM = "system"
EVENT_SOURCE_FILE = "file"
EVENT_SOURCE_VISION = "vision"

# 事件类型枚举
EVENT_TYPE_USER_MESSAGE = "user_message"
EVENT_TYPE_TOOL_RESULT = "tool_result"
EVENT_TYPE_TICK = "tick"
EVENT_TYPE_REFLECTION_RESULT = "reflection_result"
EVENT_TYPE_STATE_CHANGE = "state_change"
EVENT_TYPE_SYSTEM_SIGNAL = "system_signal"

# 模态枚举
EVENT_MODALITY_TEXT = "text"
EVENT_MODALITY_EVENT = "event"
EVENT_MODALITY_JSON = "json"
EVENT_MODALITY_IMAGE = "image"
EVENT_MODALITY_AUDIO = "audio"


@dataclass
class BrainEvent:
    """统一事件契约 — 所有刺激的统一包装。

    让 user_message / tool_result / tick / reflection_result / system_signal
    都能走同一条入口。
    """
    id: str = ""
    parent_id: str = ""   # 父事件 ID，根事件为 ""（空字符串 = 无父，以此作为根事件判据）
    trace_id: str = ""    # 链路根事件 ID，同一链路所有事件的 trace_id 应等于根事件的 id
    source: str = EVENT_SOURCE_CHAT
    type: str = EVENT_TYPE_USER_MESSAGE
    modality: str = EVENT_MODALITY_TEXT
    content: str = ""
    timestamp: str = ""
    salience: float = 0.0
    metadata: dict = field(default_factory=dict)
    raw: Any = None

    def is_root_event(self) -> bool:
        return not self.parent_id

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "trace_id": self.trace_id,
            "source": self.source,
            "type": self.type,
            "modality": self.modality,
            "content": self.content[:500],
            "timestamp": self.timestamp,
            "salience": round(self.salience, 3),
            "metadata": self.metadata,
        }


@dataclass
class BrainCycleContext:
    """单轮事件处理的完整上下文。

    包括感知→注意→记忆→状态→决策→动作→学习→反馈的完整链路。
    """
    event: BrainEvent = field(default_factory=BrainEvent)
    perception: dict = field(default_factory=dict)
    attention: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    cognition: dict = field(default_factory=dict)
    action: dict = field(default_factory=dict)
    learning: dict = field(default_factory=dict)
    feedback: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event.id,
            "source": self.event.source,
            "perception": self.perception,
            "attention": self.attention,
            "memory": self.memory,
            "state": self.state,
            "cognition": self.cognition,
            "action": self.action,
            "learning": self.learning,
            "feedback": self.feedback,
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════
# 事件工厂 — 便捷创建不同来源的 BrainEvent
# ═══════════════════════════════════════════════════════════════

def _new_event_id() -> str:
    import hashlib
    from main_brain.state import times
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:6]
    return f"evt_{stamp}_{suffix}"


def _new_trace_id() -> str:
    import hashlib
    from main_brain.state import times
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:8]
    return f"trace_{stamp}_{suffix}"


def make_chat_event(content: str, **metadata) -> BrainEvent:
    """创建用户消息事件。"""
    return BrainEvent(
        id=_new_event_id(),
        trace_id=_new_trace_id(),
        source=EVENT_SOURCE_CHAT,
        type=EVENT_TYPE_USER_MESSAGE,
        modality=EVENT_MODALITY_TEXT,
        content=content,
        timestamp=_now_iso(),
        salience=1.0,
        metadata=metadata,
    )


def make_tool_result_event(tool_name: str, result: str, parent_id: str, trace_id: str, **metadata) -> BrainEvent:
    """创建工具结果事件。"""
    return BrainEvent(
        id=_new_event_id(),
        parent_id=parent_id,
        trace_id=trace_id,
        source=EVENT_SOURCE_TOOL,
        type=EVENT_TYPE_TOOL_RESULT,
        modality=EVENT_MODALITY_JSON,
        content=result,
        timestamp=_now_iso(),
        salience=0.8,
        metadata={"tool_name": tool_name, **metadata},
    )


def make_tick_event(tick_type: str, **metadata) -> BrainEvent:
    """创建后台 tick 事件。"""
    return BrainEvent(
        id=_new_event_id(),
        trace_id=_new_trace_id(),
        source=EVENT_SOURCE_TICK,
        type=EVENT_TYPE_TICK,
        modality=EVENT_MODALITY_EVENT,
        content=f"tick:{tick_type}",
        timestamp=_now_iso(),
        salience=0.5,
        metadata={"tick_type": tick_type, **metadata},
    )


def make_reflection_event(content: str, **metadata) -> BrainEvent:
    """创建反思结果事件。"""
    return BrainEvent(
        id=_new_event_id(),
        trace_id=_new_trace_id(),
        source=EVENT_SOURCE_REFLECTION,
        type=EVENT_TYPE_REFLECTION_RESULT,
        modality=EVENT_MODALITY_TEXT,
        content=content,
        timestamp=_now_iso(),
        salience=0.6,
        metadata=metadata,
    )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════
# 聊天回复信封（T001 / FR-004）
# BrainReplyEnvelope — 大脑产出回复的统一包装
# ═══════════════════════════════════════════════════════════════

REPLY_TYPE_FINAL = "final"
REPLY_TYPE_PENDING = "pending"
REPLY_TYPE_FALLBACK = "fallback"


@dataclass
class BrainReplyEnvelope:
    """大脑产出的回复信封 — 不管回复来自哪个 action，都包装成这个结构。

    表达桥（ExpressionBridge）负责把它转成 SSE token 流。
    """
    trace_id: str = ""
    source_event_id: str = ""
    reply_type: str = REPLY_TYPE_FINAL
    text: str = ""
    chunks: list[str] = field(default_factory=list)
    should_send: bool = True
    hold_reason: str = ""
    usage: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_judge(cls, decision: "BrainJudgeDecision", event_id: str, trace_id: str) -> "BrainReplyEnvelope":
        """从 BrainJudgeDecision 构建回复信封。"""
        text = ""
        strategy = decision.reply_strategy or {}
        if isinstance(strategy, dict):
            text = strategy.get("final_reply", "") or strategy.get("text", "")
        return cls(
            trace_id=trace_id,
            source_event_id=event_id,
            reply_type=REPLY_TYPE_FINAL,
            text=text,
            should_send=bool(text),
            metadata={"confidence": decision.confidence},
        )
