"""Working Set — 近期脑海（6h TTL，多类型，Upsert）

短期缓存，支持 node / memory / open_loop 三种类型。读时自动过滤过期。
Upsert 语义（决策 #9）：同一 ref_id 已存在 → score=max(old,new)、刷新 expire_at，
不分叉出多条。

来源：search_hit / association / open_loop_trigger / recent_discussion。
Prompt："最近脑海里浮现：海马体、实体关系、长期记忆"。
"""
import logging

from .store import get_state
from .. import clock

logger = logging.getLogger('state.working_set')

WORKING_SET_TTL_HOURS = 6


class WorkingSetManager:
    """近期脑海管理器。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    def upsert(self, type_: str, ref_id: str, score: float = 0.5,
               source: str = "search_hit") -> None:
        """插入或更新一条工作记忆。

        - type_ ∈ {node, memory, open_loop}
        - ref_id：对应 node_id / episodic_id / loop_id
        - 同 ref_id 已存在：score=max，expire_at 刷新到 now+6h（不分叉）
        """
        if not ref_id:
            return
        if type_ not in ("node", "memory", "open_loop"):
            logger.warning(f"[working_set] unknown type {type_!r}, skip")
            return
        now_iso = clock.now_iso()
        expire_at = clock.now_plus_hours_iso(WORKING_SET_TTL_HOURS)
        with self._state.transaction() as data:
            ws = data.setdefault("working_set", [])
            # 顺手清掉过期项（一次写覆盖「插入 + 清理」）
            ws = [w for w in ws if w.get("expire_at", "") >= now_iso]
            for item in ws:
                if item.get("ref_id") == ref_id:
                    item["score"] = max(float(item.get("score", 0.0)), float(score))
                    item["expire_at"] = expire_at
                    item["source"] = source
                    data["working_set"] = ws
                    return
            ws.append({
                "id": f"evt_{clock.now_iso().replace(':', '').replace('-', '').replace('+', '')}",
                "type": type_,
                "ref_id": ref_id,
                "score": float(score),
                "expire_at": expire_at,
                "source": source,
            })
            data["working_set"] = ws

    def get_active(self) -> list[dict]:
        """返回未过期条目（纯读，不落盘）。"""
        now_iso = clock.now_iso()
        ws = self._state.snapshot().get("working_set", [])
        return [w for w in ws if w.get("expire_at", "") >= now_iso]

    def prune(self) -> int:
        """移除过期条目。Returns: 移除数。"""
        now_iso = clock.now_iso()
        removed = 0
        with self._state.transaction() as data:
            ws = data.get("working_set", [])
            kept = [w for w in ws if w.get("expire_at", "") >= now_iso]
            removed = len(ws) - len(kept)
            data["working_set"] = kept
        return removed

    def summary(self, limit: int = 5) -> str:
        """供 prompt 注入的摘要文本。"""
        active = sorted(self.get_active(), key=lambda w: w.get("score", 0), reverse=True)
        names = []
        for w in active[:limit]:
            ref = w.get("ref_id", "")
            # node 类型直接用实体名；memory/open_loop 用 ref_id 缩写
            names.append(ref if w.get("type") == "node" else ref[:12])
        names = [n for n in names if n]
        return "、".join(names) if names else ""
