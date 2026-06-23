"""输出记忆沉淀包 — 候选采集 / LLM 判断 / 去重 / 写入 / 轨迹

对外只导出数据契约与各子模块的工厂函数。统筹逻辑（批量沉淀流程）在
main_brain/consolidation/，调用方经该 orchestrator 访问。

边界（避免重复逻辑）：
  - 语义去重/合并交给 store 流水线的 episodic_merge（0.85）
  - 本包只做源头去重（last_processed_seq + source_hash）+ LLM 价值判断
"""
from .contracts import (
    OutputEntry, MemoryCandidate, ConsolidationRun, ConsolidationState,
    LongTermMemoryPayload,
    SOURCE_OUTPUT, SOURCE_PROACTIVE, SOURCE_REFLECTION, SOURCE_TICK,
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
    DECISION_SAVE, DECISION_UPDATE, DECISION_SKIP,
    DECISION_REDACTED, DECISION_DUPLICATE,
    TRIGGER_REACTIVE_END, TRIGGER_IDLE_TICK, TRIGGER_DAILY_TICK, TRIGGER_MANUAL,
    POLICY_VERSION, clamp,
)
from . import redaction
from .collector import collect_from_entries, normalize_text, source_hash
from .policy import ValuePolicy, get_default_policy
from .judge import ConsolidationJudge, get_consolidation_judge
from .dedupe import DedupeGate, semantic_similarity, SEMANTIC_DUP_THRESHOLD
from .writer import write_candidate
from .trace import TraceStore, get_trace_store

__all__ = [
    # contracts
    "OutputEntry", "MemoryCandidate", "ConsolidationRun", "ConsolidationState",
    "LongTermMemoryPayload",
    "SOURCE_OUTPUT", "SOURCE_PROACTIVE", "SOURCE_REFLECTION", "SOURCE_TICK",
    "MEMORY_KIND_PREFERENCE", "MEMORY_KIND_TASK", "MEMORY_KIND_FACT",
    "MEMORY_KIND_RELATION", "MEMORY_KIND_DECISION", "MEMORY_KIND_OTHER",
    "DECISION_SAVE", "DECISION_UPDATE", "DECISION_SKIP",
    "DECISION_REDACTED", "DECISION_DUPLICATE",
    "TRIGGER_REACTIVE_END", "TRIGGER_IDLE_TICK", "TRIGGER_DAILY_TICK", "TRIGGER_MANUAL",
    "POLICY_VERSION", "clamp",
    # sub-modules
    "redaction",
    "collect_from_entries", "normalize_text", "source_hash",
    "ValuePolicy", "get_default_policy",
    "ConsolidationJudge", "get_consolidation_judge",
    "DedupeGate", "semantic_similarity", "SEMANTIC_DUP_THRESHOLD",
    "write_candidate",
    "TraceStore", "get_trace_store",
]
