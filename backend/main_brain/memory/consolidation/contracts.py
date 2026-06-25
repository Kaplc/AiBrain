"""输出记忆沉淀 — 数据契约（T002）

沉淀流水线各阶段共用的数据结构（dataclass）。对应 plan 第六节「数据结构」：
  - OutputEntry          ：output.json 单条记录的归一化视图（不改动原始格式）
  - MemoryCandidate      ：从输出中抽取的一条候选记忆 + 评分 + 决策
  - ConsolidationRun     ：一次沉淀运行的统计（run_id / 计数 / 耗时）
  - ConsolidationState   ：跨运行持久化状态（检查点 / seen_hash / 冷却）
  - LongTermMemoryPayload：写入 aibrain_memories 时附带的元数据

设计要点：
  - output.json 原始格式（seq/user/assistant/time）保持不变（FR-010），source 由
    collector 推断（有 user → chat，无 user → proactive），不回写文件。
  - 去重的语义层交由 store 流水线的 episodic_merge（0.85 阈值）处理；本层只做
    源头去重（last_processed_seq + source_hash），见 dedupe.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 候选来源类型 ──────────────────────────────────────────────
SOURCE_OUTPUT = "output"        # 用户聊天输出
SOURCE_PROACTIVE = "proactive"  # 主动表达 / 无 user 的输出条目
SOURCE_REFLECTION = "reflection"  # 反思摘要（预留）
SOURCE_TICK = "tick"            # 脑循环 tick 摘要（预留）

# ── 记忆类型（写入 aibrain_memories 的 memory_kind）──────────
MEMORY_KIND_PREFERENCE = "preference"
MEMORY_KIND_TASK = "task"
MEMORY_KIND_FACT = "fact"
MEMORY_KIND_RELATION = "relation"
MEMORY_KIND_DECISION = "decision"
MEMORY_KIND_OTHER = "other"

# ── 候选决策 ──────────────────────────────────────────────────
DECISION_SAVE = "save"
DECISION_UPDATE = "update"      # v1 由 pipeline 的 merge 覆盖，本层一般不直接产出
DECISION_SKIP = "skip"          # 低分 / 短文本
DECISION_REDACTED = "redacted"  # 命中敏感屏蔽
DECISION_DUPLICATE = "duplicate"  # source_hash 已见过 / 批次内重复

# ── 触发器 ────────────────────────────────────────────────────
TRIGGER_REACTIVE_END = "reactive_end"
TRIGGER_IDLE_TICK = "idle_tick"
TRIGGER_DAILY_TICK = "daily_tick"
TRIGGER_MANUAL = "manual"

POLICY_VERSION = "v1"


@dataclass
class OutputEntry:
    """output.json 单条记录的归一化视图。

    不写入文件，仅作为采集/评分的内存对象。source 由 collector 推断。
    """
    seq: int = 0
    user: str = ""
    assistant: str = ""
    time: str = ""
    source: str = SOURCE_OUTPUT  # chat 推断：有 user → output，否则 proactive

    @classmethod
    def from_raw(cls, raw: dict) -> "OutputEntry":
        raw = raw if isinstance(raw, dict) else {}
        user = str(raw.get("user", "") or "")
        source = SOURCE_OUTPUT if user else SOURCE_PROACTIVE
        return cls(
            seq=int(raw.get("seq", 0) or 0),
            user=user,
            assistant=str(raw.get("assistant", "") or ""),
            time=str(raw.get("time", "") or ""),
            source=source,
        )


@dataclass
class MemoryCandidate:
    """一条候选记忆（抽取后 → 评分 → 决策）。"""
    candidate_id: str = ""
    source_type: str = SOURCE_OUTPUT
    source_seq: int = 0
    source_text: str = ""        # 原始片段
    summary: str = ""            # 归一化摘要（写入用）
    memory_kind: str = MEMORY_KIND_OTHER
    source_hash: str = ""        # 内容 hash（源头去重键）

    # 评分项（0-1）
    importance: float = 0.0
    novelty: float = 0.0
    persistence: float = 0.0
    relation_score: float = 0.0
    task_score: float = 0.0
    sensitivity: float = 0.0
    final_score: float = 0.0

    # 决策
    decision: str = DECISION_SKIP
    reason: str = ""
    need_llm: bool = False

    # 写入回填
    memory_id: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "source_seq": self.source_seq,
            "summary": self.summary,
            "memory_kind": self.memory_kind,
            "importance": round(self.importance, 3),
            "novelty": round(self.novelty, 3),
            "persistence": round(self.persistence, 3),
            "relation_score": round(self.relation_score, 3),
            "task_score": round(self.task_score, 3),
            "sensitivity": round(self.sensitivity, 3),
            "final_score": round(self.final_score, 3),
            "decision": self.decision,
            "reason": self.reason,
            "memory_id": self.memory_id,
        }


@dataclass
class ConsolidationRun:
    """一次沉淀运行的统计。"""
    run_id: str = ""
    trigger: str = TRIGGER_MANUAL
    tick_type: str = ""
    started_at: str = ""
    elapsed_ms: int = 0
    scanned_count: int = 0       # 扫描 output 条目数
    candidate_count: int = 0
    saved_count: int = 0
    updated_count: int = 0       # pipeline merge 命中（deleted>0）
    skipped_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    last_processed_seq: int = 0
    status: str = "success"      # success / partial / failed / dry_run
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "trigger": self.trigger,
            "tick_type": self.tick_type,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms,
            "scanned_count": self.scanned_count,
            "candidate_count": self.candidate_count,
            "saved_count": self.saved_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "duplicate_count": self.duplicate_count,
            "error_count": self.error_count,
            "last_processed_seq": self.last_processed_seq,
            "status": self.status,
            "dry_run": self.dry_run,
            "errors": self.errors[:5],
        }


@dataclass
class ConsolidationState:
    """跨运行持久化状态（落在 internal_state.json['memory_consolidation']）。"""
    last_processed_seq: int = 0
    last_run_id: str = ""
    last_saved_at: str = ""
    last_saved_memory_id: str = ""
    policy_version: str = POLICY_VERSION
    cooldown_until: str = ""
    pending_backlog: int = 0
    run_seq: int = 0             # run_id 序号
    seen_hashes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "last_processed_seq": self.last_processed_seq,
            "last_run_id": self.last_run_id,
            "last_saved_at": self.last_saved_at,
            "last_saved_memory_id": self.last_saved_memory_id,
            "policy_version": self.policy_version,
            "cooldown_until": self.cooldown_until,
            "pending_backlog": self.pending_backlog,
            "run_seq": self.run_seq,
            "seen_hashes": self.seen_hashes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConsolidationState":
        d = d if isinstance(d, dict) else {}
        return cls(
            last_processed_seq=int(d.get("last_processed_seq", 0) or 0),
            last_run_id=str(d.get("last_run_id", "") or ""),
            last_saved_at=str(d.get("last_saved_at", "") or ""),
            last_saved_memory_id=str(d.get("last_saved_memory_id", "") or ""),
            policy_version=str(d.get("policy_version", POLICY_VERSION) or POLICY_VERSION),
            cooldown_until=str(d.get("cooldown_until", "") or ""),
            pending_backlog=int(d.get("pending_backlog", 0) or 0),
            run_seq=int(d.get("run_seq", 0) or 0),
            seen_hashes=[str(h) for h in d.get("seen_hashes", []) if h],
        )


@dataclass
class LongTermMemoryPayload:
    """写入 aibrain_memories 时附带的元数据（memory_meta）。

    注意：语义去重/合并不在此处理，store 流水线的 episodic_merge 已覆盖。
    """
    source: str = SOURCE_OUTPUT
    source_seq: int = 0
    source_run_id: str = ""
    memory_kind: str = MEMORY_KIND_OTHER
    importance: float = 0.0
    tags: list[str] = field(default_factory=list)
    source_hash: str = ""

    def to_meta(self) -> dict:
        return {
            "source": self.source,
            "source_seq": self.source_seq,
            "source_run_id": self.source_run_id,
            "memory_kind": self.memory_kind,
            "importance": round(float(self.importance), 3),
            "tags": self.tags,
            "source_hash": self.source_hash,
        }


# ── 小工具 ────────────────────────────────────────────────────
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []
