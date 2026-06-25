"""价值评分策略（T005 / FR-002）

规则优先（不调 LLM）：对每个候选计算六维分数并产出决策（save / skip / redacted）。
LLM 只做可选辅助（need_llm 标记），第一版不强制（plan：不让 LLM 成为唯一判定器）。

六个维度（均 0-1）：
  - importance    重要性：稳定信息信号（偏好/事实/决定）密度
  - persistence   持续性：是否长期稳定 vs 临时
  - novelty       新颖度：与已有记忆的差异（由 dedupe 提供，默认中性 0.5）
  - task_score    任务相关性：是否含待办/承诺/未决事项
  - relation_score关系相关性：是否关系语境/期待变化
  - sensitivity   敏感风险：由 redaction 提供

最终分 = 加权和；sensitivity 超阈值则强制 redacted（跳过）。
memory_kind 按 signal 分类（preference/task/fact/relation/decision/other）。
"""
from __future__ import annotations

import re

from .contracts import (
    MemoryCandidate,
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
    DECISION_SAVE, DECISION_SKIP, DECISION_REDACTED, clamp,
)

# ── 默认阈值（可由 BrainConfig 覆盖）─────────────────────────
DEFAULT_SAVE_THRESHOLD = 0.45       # >= 即 save（规则兜底阈值，LLM 为主判断）
DEFAULT_REDACT_THRESHOLD = 0.6      # sensitivity >= 即 redacted
DEFAULT_NOVELTY_DEFAULT = 0.5       # 未知新颖度时的中性默认

# 加权（和为 1.0）
_W_IMPORTANCE = 0.32
_W_PERSISTENCE = 0.22
_W_NOVELTY = 0.18
_W_TASK = 0.14
_W_RELATION = 0.14


# ── 信号词典（中文为主，兼顾少量英文）──────────────────────
# 注意：用「词组」而非单字，降低误命中
_PREF_RE = re.compile(
    r"(?:喜欢|偏好|习惯|倾向|比较喜欢|讨厌|不喜欢|更喜|希望用|请用|用这个|"
    r"我喜欢|我习惯|我的习惯|always|prefer|习惯上)"
)
_FACT_RE = re.compile(
    r"(?:我的|我是|我在|我叫|住在|目录是|路径是|项目叫|文件在|用的是|"
    r"用的是|在用|my name|位于|存放在)"
)
_DECISION_RE = re.compile(
    r"(?:决定|就选|选这个|改成|改为|换成|不用了|不要了|确认用|就用|"
    r"默认用|已决定)"
)
_TASK_RE = re.compile(
    r"(?:要做|待办|下次|稍后|之后|继续做|记得|别忘了|帮我|计划|准备做|"
    r"todo|待会儿|一会|还没完成|没做完)"
)
_RELATION_RE = re.compile(
    r"(?:希望你|想让你|你是我的|我们是|咱们|期待你|应该你|信任你|朋友|伙伴|"
    r"搭档)"
)
# 持续性
_PERSIST_HIGH_RE = re.compile(r"(?:总是|一直|每次|常常|习惯|规则|原则|永远|都要|以后|规定|默认|长期|all the time)")
_PERSIST_LOW_RE = re.compile(r"(?:现在|今天|临时|这次|刚才|一会儿|马上|暂时|偶尔|right now)")


def _count_match(text: str, pattern: re.Pattern) -> int:
    return len(pattern.findall(text))


def _classify_kind(summary: str) -> str:
    """按命中信号给记忆分类（取优先级最高的一类）。"""
    if _count_match(summary, _DECISION_RE):
        return MEMORY_KIND_DECISION
    if _count_match(summary, _TASK_RE):
        return MEMORY_KIND_TASK
    if _count_match(summary, _PREF_RE):
        return MEMORY_KIND_PREFERENCE
    if _count_match(summary, _RELATION_RE):
        return MEMORY_KIND_RELATION
    if _count_match(summary, _FACT_RE):
        return MEMORY_KIND_FACT
    return MEMORY_KIND_OTHER


def score_importance(summary: str) -> float:
    """重要性：稳定信息信号密度（偏好/任务/事实/决定/关系任一命中都算）。

    基线 0.15，各类命中加权累加（每类按是否命中，min 1），上限 1.0。
    """
    score = 0.15
    score += 0.25 * min(1, _count_match(summary, _PREF_RE))
    score += 0.25 * min(1, _count_match(summary, _TASK_RE))
    score += 0.20 * min(1, _count_match(summary, _FACT_RE))
    score += 0.30 * min(1, _count_match(summary, _DECISION_RE))
    score += 0.25 * min(1, _count_match(summary, _RELATION_RE))
    return clamp(score)


def score_persistence(summary: str) -> float:
    """持续性：长期标记 → 高；临时标记且无长期 → 低；否则中性。"""
    high = _count_match(summary, _PERSIST_HIGH_RE)
    low = _count_match(summary, _PERSIST_LOW_RE)
    if high:
        return clamp(0.85)
    if low:
        return clamp(0.25)
    return 0.5


def score_task(summary: str) -> float:
    return clamp(0.85) if _count_match(summary, _TASK_RE) else 0.2


def score_relation(summary: str) -> float:
    return clamp(0.85) if _count_match(summary, _RELATION_RE) else 0.2


def final_score(c: MemoryCandidate, *, novelty: float | None = None) -> float:
    """综合分（不含 sensitivity 惩罚；sensitivity 在决策时单独处理）。"""
    nov = novelty if novelty is not None else c.novelty
    return clamp(
        _W_IMPORTANCE * c.importance
        + _W_PERSISTENCE * c.persistence
        + _W_NOVELTY * nov
        + _W_TASK * c.task_score
        + _W_RELATION * c.relation_score
    )


class ValuePolicy:
    """价值评分策略（可配置阈值）。无状态。"""

    def __init__(
        self,
        *,
        save_threshold: float = DEFAULT_SAVE_THRESHOLD,
        redact_threshold: float = DEFAULT_REDACT_THRESHOLD,
        novelty_default: float = DEFAULT_NOVELTY_DEFAULT,
    ):
        self.save_threshold = save_threshold
        self.redact_threshold = redact_threshold
        self.novelty_default = novelty_default

    def score(self, candidate: MemoryCandidate, *, novelty: float | None = None) -> MemoryCandidate:
        """原地填充候选的评分项 + memory_kind + final_score（不改 decision）。"""
        s = candidate.summary
        candidate.memory_kind = _classify_kind(s)
        candidate.importance = score_importance(s)
        candidate.persistence = score_persistence(s)
        candidate.task_score = score_task(s)
        candidate.relation_score = score_relation(s)
        nov = novelty if novelty is not None else candidate.novelty or self.novelty_default
        candidate.novelty = clamp(nov)
        candidate.final_score = final_score(candidate, novelty=candidate.novelty)
        return candidate

    def decide(self, candidate: MemoryCandidate) -> tuple[str, str, bool]:
        """返回 (decision, reason, need_llm)。

        - sensitivity >= redact_threshold → redacted
        - final_score >= save_threshold → save
        - 否则 → skip（低价值）
        need_llm：分数落在阈值附近 ±0.05 的灰色地带，标记可让 LLM 复核（v1 不调用）。
        """
        if candidate.sensitivity >= self.redact_threshold:
            return (DECISION_REDACTED, f"敏感风险 {candidate.sensitivity:.2f} 超阈值", False)

        if candidate.final_score >= self.save_threshold:
            in_gray = abs(candidate.final_score - self.save_threshold) <= 0.05
            reason = (f"分 {candidate.final_score:.2f} 达阈值 "
                      f"({candidate.memory_kind}/重要性{candidate.importance:.2f}"
                      f"/持续{candidate.persistence:.2f})")
            return (DECISION_SAVE, reason, in_gray)

        return (DECISION_SKIP,
                f"分 {candidate.final_score:.2f} 低于阈值 "
                f"({candidate.memory_kind}/重要性{candidate.importance:.2f})",
                False)


def get_default_policy() -> ValuePolicy:
    """默认策略实例。"""
    return ValuePolicy()
