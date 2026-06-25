"""Goals — 长期方向（只做 goal_bias，不修改 Concern）

关键约束（plan 模块 1 / 决策 #3）：Goal 代表长期方向，Concern 代表近期真实
兴趣，两者分开。Goal 【不】给 Concern 维持地板或加性 boost，只在搜索时加
轻量 goal_bias = goal.priority × 0.01（priority=0.95→0.0095）。

bias 取所有 related_concepts 命中的 goal 里【最高 priority】×0.01（max 而非
sum，避免多目标叠加膨胀）。related_concepts 与候选记忆实体做名字匹配。
"""
import logging

from .store import get_state

logger = logging.getLogger('state.goals')

GOAL_BIAS_WEIGHT = 0.01


class GoalManager:
    """目标管理器（只读；目标由人手工或 V2 维护）。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    def get_all(self) -> list[dict]:
        return self._state.snapshot().get("goals", [])

    def goal_bias_for_entities(self, entity_names: list[str]) -> float:
        """命中的最高优先级 goal × 0.01。无命中返回 0。

        匹配规则：goal.related_concepts 中任一概念名出现在候选记忆的实体名里
        （双向子串匹配，兼容 related_concepts 与 entity 命名不完全一致的情况）。
        """
        if not entity_names:
            return 0.0
        goals = self.get_all()
        if not goals:
            return 0.0
        ents = [e for e in entity_names if e]
        best = 0.0
        for g in goals:
            concepts = g.get("related_concepts", []) or []
            if not concepts:
                continue
            if _any_concept_hits(concepts, ents):
                best = max(best, float(g.get("priority", 0.0)))
        return round(best * GOAL_BIAS_WEIGHT, 4)

    def summary_lines(self, limit: int = 3) -> list[str]:
        """供 prompt 注入的目标摘要。"""
        lines = []
        for g in self.get_all()[:limit]:
            name = g.get("name", "")
            concepts = "、".join((g.get("related_concepts") or [])[:4])
            lines.append(f"• {name}（关注：{concepts}）" if concepts else f"• {name}")
        return lines


def _any_concept_hits(concepts: list[str], entities: list[str]) -> bool:
    """related_concepts 与 entities 是否有名字交集（子串匹配）。"""
    ent_set = [e for e in entities if e]
    for c in concepts:
        if not c:
            continue
        for e in ent_set:
            if c in e or e in c:
                return True
    return False
