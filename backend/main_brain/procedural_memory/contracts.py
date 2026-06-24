"""程序记忆模块数据合约"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ── 状态枚举 ─────────────────────────────────────────────

TEMPLATE_STATUS = ("draft", "proposed", "active", "cooling", "deprecated", "archive")
RISK_LEVELS = ("low", "medium", "high")
OUTCOMES = ("success", "fail", "partial", "unknown")


# ── 核心合约 ─────────────────────────────────────────────

@dataclass
class ProcedureExample:
    """单次运行样本，来自 brain_runs.jsonl 的归一化表示"""
    example_id: str
    run_id: str
    mode: str                              # reactive / background
    tick_type: str = ""
    context_digest: dict = field(default_factory=dict)
    action_sequence: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    state_deltas: list[dict] = field(default_factory=list)
    outcome: str = "unknown"
    reward: float = 0.0
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProcedureExample":
        return ProcedureExample(**d)


@dataclass
class ProcedureTemplate:
    """从相似样本中提炼出的动作模板"""
    template_id: str
    name: str
    intent: str
    trigger_signals: dict = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    risk_level: str = "low"
    status: str = "draft"
    confidence: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    reward_ema: float = 0.0
    last_used_at: str = ""
    last_mined_at: str = ""
    version: int = 1
    tags: list[str] = field(default_factory=list)
    source_example_ids: list[str] = field(default_factory=list)
    skill_exportable: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProcedureTemplate":
        return ProcedureTemplate(**d)


@dataclass
class ProcedureMatch:
    """匹配结果，描述一个模板与当前上下文的适配程度"""
    match_id: str
    template_id: str
    score: float = 0.0
    context_fit: float = 0.0
    success_fit: float = 0.0
    risk_penalty: float = 0.0
    reason: str = ""
    step_preview: list[str] = field(default_factory=list)
    action_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProcedureMatch":
        return ProcedureMatch(**d)


@dataclass
class ProcedureFeedback:
    """单次反馈记录"""
    template_id: str
    run_id: str
    result: str = "unknown"
    reward_delta: float = 0.0
    notes: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcedureState:
    """程序记忆模块自身的运行状态检查点"""
    last_mined_run_id: str = ""
    last_example_seq: int = 0
    last_template_id: str = ""
    policy_version: str = "1.0"
    active_count: int = 0
    draft_count: int = 0
    archive_count: int = 0
    cooldown_until: str = ""
    export_queue_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProcedureState":
        return ProcedureState(**d)
