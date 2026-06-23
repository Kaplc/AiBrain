"""去重 / 冷却（T006 / FR-004 / FR-008）

重要边界：**语义去重交给 store 流水线的 episodic_merge（0.85 阈值）**，本层不重复做。
本层只做流水线不管的三类「源头去重」，目的是避免对已沉淀内容反复调用 store_memory
（每次调用都要 embed + 语义搜索 + merge，成本不低）：

  1. source_hash 去重（跨 run / 跨重启）：seen_hashes 持久化在 ConsolidationState，
     命中即 duplicate，cheap 跳过。
  2. 批次内 hash 去重：同一次 run 抽到相同文本，内存 set 拦截。
  3. 语义预筛（仅对已过 save 阈值的高分候选）：search_memory 取相似度，既算 novelty，
     又在极高相似（>= 0.88）时直接判 duplicate，省掉一次 store 写入。0.85~0.88 区间
     交给 pipeline 的 merge 处理（计入 updated）。

novelty = 1 - top_similarity，作为 policy 的一个评分维度。
"""
from __future__ import annotations

import logging

from .contracts import MemoryCandidate, clamp

logger = logging.getLogger("memory.consolidation.dedupe")

# 极高相似 → 直接判 duplicate（高于 pipeline 的 0.85，留 merge 带给流水线）
SEMANTIC_DUP_THRESHOLD = 0.88
# 默认 novelty（语义检查失败 / 跳过时）
NOVELTY_DEFAULT = 0.5


def semantic_similarity(summary: str) -> tuple[float, str]:
    """对摘要做一次语义检索，返回 (top_score, top_id)。

    失败（Qdrant 不可用等）返回 (0.0, "")，调用方按默认 novelty 处理，不阻断流程。
    """
    if not summary:
        return 0.0, ""
    try:
        from modules.brain.memory import search_memory
        hits = search_memory(summary)
    except Exception as e:
        logger.warning(f"[dedupe] semantic search failed: {e}")
        return 0.0, ""
    if not hits:
        return 0.0, ""
    top = max(hits, key=lambda h: float(h.get("score", 0.0) or 0.0))
    return clamp(float(top.get("score", 0.0) or 0.0)), str(top.get("id", "") or "")


class DedupeGate:
    """源头去重闸门：seen_hash（来自 state）+ 批次内 hash + 语义预筛。"""

    def __init__(
        self,
        *,
        seen_hashes: set[str] | None = None,
        semantic_check: bool = True,
        dup_threshold: float = SEMANTIC_DUP_THRESHOLD,
    ):
        # 跨 run 已见 hash（来自持久化 state）
        self._seen: set[str] = set(seen_hashes or [])
        # 批次内 hash（仅本次 run）
        self._batch: set[str] = set()
        self._semantic_check = semantic_check
        self._dup_threshold = dup_threshold
        # 本次新增的 hash（run 结束后写回 state）
        self._newly_added: set[str] = set()

    @property
    def newly_added_hashes(self) -> set[str]:
        return set(self._newly_added)

    def _hash_seen(self, h: str) -> bool:
        return h in self._seen or h in self._batch

    def _mark(self, h: str) -> None:
        self._batch.add(h)
        self._newly_added.add(h)

    def check(self, candidate: MemoryCandidate) -> tuple[str, float, str]:
        """对候选做源头去重 + 语义预筛。

        Returns:
            (status, novelty, reason)
            status ∈ {"duplicate", "fresh"}
            novelty ∈ [0,1]（语义检查未做/失败时为 NOVELTY_DEFAULT）
        """
        h = candidate.source_hash

        # 1. 批次内 / 跨 run hash 重复
        if self._hash_seen(h):
            return ("duplicate", NOVELTY_DEFAULT, "source_hash 已见过")

        # 2. 语义预筛（仅高分候选调用，见 orchestrator 的调用时机）
        if self._semantic_check:
            top_score, top_id = semantic_similarity(candidate.summary)
            novelty = clamp(1.0 - top_score)
            if top_score >= self._dup_threshold:
                # 极高相似 → 已有等价记忆，跳过写入（pipeline 也会 merge，这里省一次写）
                return ("duplicate", novelty,
                        f"语义高度相似 score={top_score:.2f} id={top_id[:8]}")
        else:
            novelty = NOVELTY_DEFAULT

        # 3. 标记并放行
        self._mark(h)
        return ("fresh", novelty, "")
