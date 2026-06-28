"""Open Loops — 未解问题（带 Jaccard Merge）

创建规则（plan 模块 3）：
  - 必须是问句（含 ?/？或 为什么/怎么/吗/呢/是不是/能不能）
  - 且（至少 1 个 concept 节点 或 ≥2 个节点）——过滤「吃了吗」这类无意义问句

Merge（决策 #8）：创建前遍历已有 open loops，算 Jaccard = |A∩B|/|A∪B|。
> 0.5 → 不新建，给原条目 thought_count+1。Jaccard 而非 |A∩B|/min(|A|,|B|)，
避免稀疏集 [a,b] 被并进丰富集 [a,b,c,d]（Jaccard=2/4=0.5 不 merge）。

tension（运行时，不存盘）：avg(effective_activation_of_node_ids) × uncertainty。
uncertainty 由问句词估算：为什么/怎么→0.9，是不是/能不能→0.7，吗/呢/其它→0.5。
"""
import logging

from .store import get_state
from .. import clock

logger = logging.getLogger('state.open_loops')

MERGE_JACCARD_THRESHOLD = 0.5


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _is_question(content: str) -> bool:
    if not content:
        return False
    if content.rstrip().endswith(("?", "？")):
        return True
    for kw in ("为什么", "怎么", "吗", "呢", "是不是", "能不能", "如何", "为何"):
        if kw in content:
            return True
    return False


def _estimate_uncertainty(content: str) -> float:
    c = content or ""
    if "为什么" in c or "怎么" in c or "如何" in c or "为何" in c:
        return 0.9
    if "是不是" in c or "能不能" in c:
        return 0.7
    return 0.5  # 吗/呢/其它问句


class OpenLoopManager:
    """未解问题管理器。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    # ── 创建（带 Merge）──────────────────────────────────

    def create(self, content: str, node_ids: list[str]) -> dict | None:
        """创建一条 open loop；命中 Merge 阈值则合并进旧条目。

        创建规则不过关返回 None；合并或新建成功返回对应 loop dict。
        """
        content = (content or "").strip()
        node_ids = [n for n in (node_ids or []) if n]
        if not self._meets_creation_rule(content, node_ids):
            logger.info(f"[open_loops] reject (not qualified): {content[:30]!r}")
            return None

        with self._state.transaction() as data:
            loops = data.setdefault("open_loops", [])
            # Merge 检查
            for loop in loops:
                if loop.get("status") != "open":
                    continue
                if _jaccard(node_ids, loop.get("node_ids", [])) > MERGE_JACCARD_THRESHOLD:
                    loop["thought_count"] = loop.get("thought_count", 1) + 1
                    loop["last_thought_at"] = clock.now_iso()
                    logger.info(f"[open_loops] merge into existing {loop.get('id')} (Jaccard>{MERGE_JACCARD_THRESHOLD})")
                    return loop

            loop = {
                "id": f"loop_{clock.now_iso().replace(':', '').replace('-', '').replace('+', '')}",
                "content": content,
                "node_ids": node_ids,
                "uncertainty": _estimate_uncertainty(content),
                "last_thought_at": clock.now_iso(),
                "thought_count": 1,
                "created_at": clock.now_iso()[:10],
                "status": "open",
            }
            loops.append(loop)
        logger.info(f"[open_loops] created: {content[:40]!r} nodes={node_ids}")
        return loop

    def _meets_creation_rule(self, content: str, node_ids: list[str]) -> bool:
        """问句 且（有 concept 节点 或 ≥2 节点）。"""
        if not _is_question(content):
            return False
        if len(node_ids) >= 2:
            return True
        if len(node_ids) == 1 and self._has_concept_node(node_ids):
            return True
        return False

    def _has_concept_node(self, node_ids: list[str]) -> bool:
        """node_ids 中是否存在 concept 类型的实体节点。图不可用时视作 True（放行）。"""
        try:
            from main_brain.memory.graph import get_graph
            g = get_graph()
            if g is None:
                return True
            ph = ",".join("?" * len(node_ids))
            rows = g._exec(
                f"SELECT name FROM entity_nodes WHERE name IN ({ph}) "
                f"AND type IN ('concept','project','emotion','goal','exp')",
                tuple(node_ids),
            )
            return bool(rows)
        except Exception as e:
            logger.warning(f"[open_loops] concept check failed: {e}")
            return True

    # ── 运行时张力 ────────────────────────────────────────

    def tension(self, loop: dict) -> float:
        """tension = avg(node_ids 的 effective_activation) × uncertainty。"""
        from . import get_concerns
        concerns = get_concerns()
        node_ids = loop.get("node_ids", [])
        if not node_ids:
            return 0.0
        avg = sum(concerns.get_effective(n) for n in node_ids) / len(node_ids)
        return round(avg * float(loop.get("uncertainty", 0.5)), 4)

    # ── 维护 ──────────────────────────────────────────────

    def add_thought(self, loop_id: str):
        with self._state.transaction() as data:
            for loop in data.get("open_loops", []):
                if loop.get("id") == loop_id:
                    loop["thought_count"] = loop.get("thought_count", 1) + 1
                    loop["last_thought_at"] = clock.now_iso()
                    return True
        return False

    def resolve(self, loop_id: str):
        with self._state.transaction() as data:
            for loop in data.get("open_loops", []):
                if loop.get("id") == loop_id:
                    loop["status"] = "resolved"
                    return True
        return False

    def get_open(self) -> list[dict]:
        data = self._state.snapshot()
        return [l for l in data.get("open_loops", []) if l.get("status") == "open"]

    def summary_lines(self, limit: int = 3) -> list[str]:
        """按 tension 降序取前 N，供 prompt 注入。"""
        loops = self.get_open()
        ranked = sorted(loops, key=self.tension, reverse=True)[:limit]
        return [f"• {l['content']}" for l in ranked if l.get("content")]
