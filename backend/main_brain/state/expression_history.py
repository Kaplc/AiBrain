"""Refractory — 表达冷却期（独立于 Pending 存储）

关键设计（plan 模块 6 / 决策 #7）：
  - 独立存储在 expression_history 列表，【不】挂在 pending entry 上。
    删除 pending 不影响冷却；冷却到期也不依赖 pending 是否还在。
  - key = {expression_type}:{node_id}（概念上）。recent_interest 冷却【不】阻断
    open_loop 表达——同一节点不同表达类型各自独立计时。
  - 默认 24h，可按类型/场景缩短（如 12h）。
  - 判断：now < refractory_until → 在冷却内（novelty=0）。
"""
import logging

from .store import get_state
from .. import clock

logger = logging.getLogger('state.refractory')

DEFAULT_REFRACTORY_HOURS = 24


class ExpressionHistoryManager:
    """表达冷却管理器。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    @staticmethod
    def _key(expression_type: str, node_id: str) -> str:
        return f"{expression_type}:{node_id}"

    def is_in_refractory(self, expression_type: str, node_id: str) -> bool:
        """该 (type, node_id) 是否还在冷却期内。"""
        key = self._key(expression_type, node_id)
        now_iso = clock.now_iso()
        for h in self._state.snapshot().get("expression_history", []):
            if h.get("key") == key:
                return h.get("refractory_until", "") > now_iso
        return False

    def record(self, expression_type: str, node_id: str,
               hours: float = DEFAULT_REFRACTORY_HOURS) -> None:
        """记录一次表达，设置冷却窗口（覆盖旧记录）。"""
        if not expression_type or not node_id:
            return
        key = self._key(expression_type, node_id)
        now_iso = clock.now_iso()
        until = clock.now_plus_hours_iso(hours)
        with self._state.transaction() as data:
            hist = data.setdefault("expression_history", [])
            for h in hist:
                if h.get("key") == key:
                    h["node_id"] = node_id
                    h["expression_type"] = expression_type
                    h["last_expressed"] = now_iso
                    h["refractory_until"] = until
                    return
            hist.append({
                "key": key,
                "node_id": node_id,
                "expression_type": expression_type,
                "last_expressed": now_iso,
                "refractory_until": until,
            })

    def prune(self) -> int:
        """移除已过冷却期的记录。Returns: 移除数。"""
        now_iso = clock.now_iso()
        removed = 0
        with self._state.transaction() as data:
            hist = data.get("expression_history", [])
            kept = [h for h in hist if h.get("refractory_until", "") > now_iso]
            removed = len(hist) - len(kept)
            data["expression_history"] = kept
        return removed
