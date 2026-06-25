"""程序记忆内存索引

提供快速过滤和排序能力，每次 store 变更后通过 refresh() 重建索引。

索引维度：
  - status_idx   : status -> list[template_id]
  - risk_idx     : risk_level -> list[template_id]
  - tag_idx      : tag -> list[template_id]
  - context_sig  : trigger_signals.signature -> template_id（用于精确匹配）
  - sorted_score : 按 reward_ema 预排序的模板 ID 列表（用于淘汰候选）
"""

import logging
from collections import defaultdict
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate

logger = logging.getLogger("main_brain.memory.procedural.index")


class ProcedureIndex:
    """程序记忆内存索引，支持模板的快速过滤和排序"""

    def __init__(self):
        self._templates: dict[str, ProcedureTemplate] = {}
        self._status_idx: dict[str, list[str]] = defaultdict(list)
        self._risk_idx: dict[str, list[str]] = defaultdict(list)
        self._tag_idx: dict[str, list[str]] = defaultdict(list)
        self._context_sig: dict[str, str] = {}
        self._sorted_by_score: list[str] = []
        self._dirty = True

    # ── 构建 / 刷新 ──────────────────────────────────────

    def refresh(self, templates: list[ProcedureTemplate]):
        """用当前所有模板重建索引"""
        self._templates = {t.template_id: t for t in templates}
        count = len(templates)
        logger.debug("[index] refreshed %d templates", count)

        self._status_idx.clear()
        self._risk_idx.clear()
        self._tag_idx.clear()
        self._context_sig.clear()

        for t in templates:
            self._status_idx[t.status].append(t.template_id)
            self._risk_idx[t.risk_level].append(t.template_id)

            sig = t.trigger_signals.get("signature", "")
            if sig:
                self._context_sig[sig] = t.template_id

            for tag in t.tags:
                self._tag_idx[tag].append(t.template_id)

        # 按 reward_ema 降序预排序
        self._sorted_by_score = sorted(
            [t.template_id for t in templates],
            key=lambda tid: self._templates[tid].reward_ema,
            reverse=True,
        )
        self._dirty = False

    def mark_dirty(self):
        self._dirty = True

    # ── 查询 ─────────────────────────────────────────────

    def by_status(self, *statuses: str) -> list[ProcedureTemplate]:
        ids = set()
        for s in statuses:
            ids.update(self._status_idx.get(s, []))
        return [self._templates[i] for i in ids if i in self._templates]

    def by_risk(self, *levels: str) -> list[ProcedureTemplate]:
        ids = set()
        for r in levels:
            ids.update(self._risk_idx.get(r, []))
        return [self._templates[i] for i in ids if i in self._templates]

    def by_tag(self, tag: str) -> list[ProcedureTemplate]:
        ids = self._tag_idx.get(tag, [])
        return [self._templates[i] for i in ids if i in self._templates]

    def by_signature(self, sig: str) -> Optional[ProcedureTemplate]:
        tid = self._context_sig.get(sig)
        if tid and tid in self._templates:
            return self._templates[tid]
        return None

    def top_score(self, n: int = 10, min_confidence: float = 0.0) -> list[ProcedureTemplate]:
        """返回 reward_ema 最高的 n 个模板"""
        results = []
        for tid in self._sorted_by_score:
            t = self._templates.get(tid)
            if t and t.confidence >= min_confidence:
                results.append(t)
            if len(results) >= n:
                break
        return results

    def all_valid(self) -> list[ProcedureTemplate]:
        """返回所有可用于匹配的模板（proposed / active / cooling）"""
        return self.by_status("proposed", "active", "cooling")

    def total_count(self) -> int:
        return len(self._templates)

    def status_counts(self) -> dict[str, int]:
        counts = {}
        for s, ids in self._status_idx.items():
            counts[s] = len(ids)
        return counts
