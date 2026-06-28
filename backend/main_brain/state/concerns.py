"""Current Concerns — 当前关注层（唯一正确的「此刻在意什么」）

核心设计（见 plan 模块 2 / 决策 1-2）：
  - 存 base_activation：全部 boost 的原始累加，【不衰减写入】，有 min(1.0) 上限。
  - 运行时算 effective = base × 0.78^days_since_last_activated（温度，随时间冷却）。
  - 只存一个时间字段 last_activated，既是 dormancy 来源也是衰减基准。
  - 移除条件：effective < 0.05 且 last_activated > 180 天（防丢长期兴趣历史）。

激活：
  - activate(node_id, boost=0.15)     收到用户消息后，对涉及实体激活
  - self_activate(node_id)            猫猫自己回复时回灌，boost=0.002（防自激爆炸）

bias：搜索时记忆若命中高 concern 实体 → 加 concern_bias（见 graph_recall）。
"""
import logging

from .store import get_state
from .. import clock

logger = logging.getLogger('state.concerns')

# ── 可调参数 ──────────────────────────────────────────────
ACTIVATION_BOOST_USER = 0.15   # 用户消息触发
ACTIVATION_BOOST_SELF = 0.002  # 猫猫自回复回灌（决策 #11）
DECAY_PER_DAY = 0.78           # effective 每天乘以 0.78
EFFECTIVE_REMOVE_THRESHOLD = 0.05
DORMANCY_DAYS_REMOVE = 180
CONCERN_BIAS_WEIGHT = 0.005    # 搜索偏置权重（决策 #5）


class ConcernManager:
    """当前关注管理器。所有写操作经 state.transaction() 原子落盘。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    # ── 激活 ──────────────────────────────────────────────

    def activate(self, node_id: str, boost: float = ACTIVATION_BOOST_USER) -> float:
        """激活一个节点：base += boost（上限 1.0），刷新 last_activated。

        Returns: 激活后的 base_activation
        """
        if not node_id:
            return 0.0
        with self._state.transaction() as data:
            concerns = data.setdefault("concerns", [])
            entry = next((c for c in concerns if c.get("node_id") == node_id), None)
            now_iso = clock.now_iso()
            if entry is None:
                entry = {
                    "node_id": node_id,
                    "base_activation": min(1.0, boost),
                    "last_activated": now_iso,
                }
                concerns.append(entry)
            else:
                entry["base_activation"] = min(1.0, entry.get("base_activation", 0.0) + boost)
                entry["last_activated"] = now_iso
            base = entry["base_activation"]
        logger.info(f"[concerns] activate {node_id!r} +{boost} -> base={base:.3f}")
        return base

    def self_activate(self, node_id: str) -> float:
        """猫猫自回复回灌（boost=0.002）。"""
        return self.activate(node_id, boost=ACTIVATION_BOOST_SELF)

    # ── 运行时计算（只读，不落盘）────────────────────────

    def get_base(self, node_id: str) -> float:
        data = self._state.snapshot()
        entry = next((c for c in data.get("concerns", []) if c.get("node_id") == node_id), None)
        return entry.get("base_activation", 0.0) if entry else 0.0

    def get_effective(self, node_id: str) -> float:
        """effective = base × 0.78^days。无记录返回 0。"""
        data = self._state.snapshot()
        entry = next((c for c in data.get("concerns", []) if c.get("node_id") == node_id), None)
        if not entry:
            return 0.0
        base = entry.get("base_activation", 0.0)
        days = clock.days_since(entry.get("last_activated"))
        return round(base * (DECAY_PER_DAY ** days), 4)

    def get_dormancy(self, node_id: str) -> float:
        """dormancy = min(1.0, hours_since_last_activated / 24)。"""
        data = self._state.snapshot()
        entry = next((c for c in data.get("concerns", []) if c.get("node_id") == node_id), None)
        if not entry:
            return 1.0
        hours = clock.hours_since(entry.get("last_activated"))
        return round(min(1.0, hours / 24.0), 4)

    def concern_map(self) -> dict[str, float]:
        """{node_id: effective} 全量快照，供搜索 bias / pending 使用。"""
        data = self._state.snapshot()
        return {c["node_id"]: self.get_effective(c["node_id"]) for c in data.get("concerns", [])}

    def all_effective(self, limit: int = 50) -> list[tuple[str, float]]:
        """[(node_id, effective)] 按 effective 降序。"""
        items = sorted(self.concern_map().items(), key=lambda kv: kv[1], reverse=True)
        return items[:limit]

    # ── 搜索偏置 ──────────────────────────────────────────

    def concern_bias_for_entities(self, entity_names: list[str]) -> float:
        """一条候选记忆的 concern 偏置 = sum(命中的 effective) × 0.005。

        示例（验收）：5 个实体各 effective=0.8 → (5×0.8)×0.005 = 0.02。
        权重已足够小（最大约 0.025），不会压过 semantic/IDF/importance 分，
        故不再额外归一化（plan 决策 #4 的意图由小权重本身满足）。
        """
        if not entity_names:
            return 0.0
        cmap = self.concern_map()
        total = sum(cmap.get(n, 0.0) for n in entity_names)
        return round(total * CONCERN_BIAS_WEIGHT, 4)

    # ── 实体解析 ──────────────────────────────────────────

    def resolve_name_to_node_id(self, name: str) -> str | None:
        """向 entity_nodes 校验实体名是否真实存在（node_id == entity name）。

        图可用且确实存在 → 返回该 name；图不可用/查询出错 → best-effort 原样返回
        name（保持激活可用，不因图临时不可用而丢关注）；图可用但不存在 → None。
        """
        if not name:
            return None
        name = name.strip()
        try:
            from main_brain.memory.graph import get_graph
            g = get_graph()
            if g is None:
                return name  # 图未初始化，best-effort
            rows = g._exec("SELECT name FROM entity_nodes WHERE name = ?", (name,))
            return rows[0][0] if rows else None
        except Exception as e:
            logger.warning(f"[concerns] resolve failed for {name!r}: {e}")
            return name  # 出错 best-effort

    # ── 清理 ──────────────────────────────────────────────

    def prune(self) -> int:
        """移除 effective<0.05 且 last_activated>180天 的关注。Returns: 移除数。"""
        removed = 0
        with self._state.transaction() as data:
            concerns = data.get("concerns", [])
            kept = []
            for c in concerns:
                base = c.get("base_activation", 0.0)
                days = clock.days_since(c.get("last_activated"))
                eff = base * (DECAY_PER_DAY ** days)
                if eff < EFFECTIVE_REMOVE_THRESHOLD and days > DORMANCY_DAYS_REMOVE:
                    removed += 1
                    logger.info(f"[concerns] prune {c.get('node_id')!r} eff={eff:.3f} days={days:.0f}")
                else:
                    kept.append(c)
            data["concerns"] = kept
        return removed

    def stats(self) -> dict:
        data = self._state.snapshot()
        concerns = data.get("concerns", [])
        return {
            "total": len(concerns),
            "active": sum(1 for c in concerns if self.get_effective(c["node_id"]) >= 0.1),
            "top": self.all_effective(5),
        }
