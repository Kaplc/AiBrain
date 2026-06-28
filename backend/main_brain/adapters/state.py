"""State Adapter（T007）— 包装现有内部状态层，不复制 manager。

LifeState 落在 internal_state.json['life'] 节点（loop 控制字段）。
working_set / open_loops / goals / pending 等仍由现有 manager 持有，本 adapter
读取时【合并】进 LifeState 视图给 judge，写入时【路由】到对应 manager——不重复存储
（遵守「逻辑链不能有重复」约束）。

所有写经 get_state().transaction() 原子落盘，失败降级不抛穿。
"""
from __future__ import annotations

import logging

from ..contracts import (
    BrainJudgeDecision, BrainRunContext, default_life_state,
)

logger = logging.getLogger("main_brain.adapter.state")

# life 节点可直接覆盖的字段（标量/小对象）
_LIFE_NODE_FIELDS = (
    "life_loop_status", "current_activity", "current_focus", "focus_since",
    "last_activity_at", "last_user_contact_at", "idle_seconds", "autonomy_level",
    "energy", "mood", "relationship_context", "self_narrative_summary",
    "last_proactive_contact_at", "next_wake_hint", "last_error",
    "stream_of_consciousness",
)
RECENT_THOUGHTS_CAP = 20


class StateAdapter:
    """LifeState 读写 + judge state_updates 路由。"""

    # ── 读 ─────────────────────────────────────────────────
    def read_life_state(self) -> dict:
        """合并 life 节点 + 现有 manager 视图，给 judge/context 用。"""
        life = self._life_node()
        merged = dict(life)
        try:
            from main_brain.state import (
                get_working_set, get_open_loops, get_goals, get_pending,
                get_drives,
            )
            merged["drives"] = get_drives().get_all()
            merged["working_set"] = get_working_set().get_active()
            merged["open_loops"] = get_open_loops().get_open()
            merged["goals"] = get_goals().get_all()
            merged["pending_expressions"] = get_pending().get_unexpressed()
        except Exception as e:
            logger.warning(f"[state_adapter] enrich life_state failed: {e}")
        return merged

    def _life_node(self) -> dict:
        """读 life 节点，缺失则初始化默认骨架。"""
        try:
            from main_brain.state import get_state
            data = get_state().snapshot()
            life = data.get("life")
            if not isinstance(life, dict):
                # 首次：写默认骨架
                life = default_life_state()
                self.update_life_node(life)
            return dict(life)
        except Exception as e:
            logger.warning(f"[state_adapter] read life node failed: {e}")
            return default_life_state()

    # ── 写（life 节点）─────────────────────────────────────
    def update_life_node(self, delta: dict) -> dict:
        """合并 delta 到 life 节点（浅合并标量字段）。返回合并后的 life。"""
        if not isinstance(delta, dict) or not delta:
            return self._life_node()
        try:
            from main_brain.state import get_state
            with get_state().transaction() as data:
                life = data.setdefault("life", default_life_state())
                for k, v in delta.items():
                    if k in _LIFE_NODE_FIELDS:
                        life[k] = v
                return dict(life)
        except Exception as e:
            logger.warning(f"[state_adapter] update life node failed: {e}")
            return self._life_node()

    def append_recent_thought(self, summary: str, *, focus: str = "",
                              source: str = "") -> None:
        """往 life.recent_thoughts 追加一条摘要（cap 20，FIFO）。"""
        if not summary:
            return
        try:
            from main_brain.state import get_state
            from main_brain.clock import now_iso
            with get_state().transaction() as data:
                life = data.setdefault("life", default_life_state())
                thoughts = life.setdefault("recent_thoughts", [])
                thoughts.append({
                    "summary": summary[:200],
                    "focus": focus[:80],
                    "source": source,
                    "at": now_iso(),
                })
                if len(thoughts) > RECENT_THOUGHTS_CAP:
                    del thoughts[: len(thoughts) - RECENT_THOUGHTS_CAP]
        except Exception as e:
            logger.warning(f"[state_adapter] append thought failed: {e}")

    # ── 意识流（stream_of_consciousness）──────────────────
    def read_stream(self) -> dict:
        """读意识流字段（带默认值，缺键补齐）。供 autonomous_mind 构建上下文。"""
        stream = self._life_node().get("stream_of_consciousness") or {}
        if not isinstance(stream, dict):
            stream = {}
        return {
            "last_thought": stream.get("last_thought", ""),
            "mood": stream.get("mood", "平静"),
            "focus": stream.get("focus", ""),
            "internal_dialogue": list(stream.get("internal_dialogue") or []),
            "activities": list(stream.get("activities") or []),
            "working_memory": list(stream.get("working_memory") or []),
        }

    def mutate_stream(self, fn) -> dict:
        """事务性读改写 life['stream_of_consciousness']。

        fn(stream) 在事务内就地修改 stream（已补齐全部子键），返回修改后的快照。
        任何异常都不抛穿主流程（意识流只是辅助上下文，不应阻塞 tick）。
        """
        try:
            from main_brain.state import get_state
            with get_state().transaction() as data:
                life = data.setdefault("life", default_life_state())
                stream = life.get("stream_of_consciousness")
                if not isinstance(stream, dict):
                    stream = {}
                stream.setdefault("last_thought", "")
                stream.setdefault("mood", "平静")
                stream.setdefault("focus", "")
                stream.setdefault("internal_dialogue", [])
                stream.setdefault("activities", [])
                stream.setdefault("working_memory", [])
                fn(stream)
                life["stream_of_consciousness"] = stream
                return dict(stream)
        except Exception as e:
            logger.warning(f"[state_adapter] mutate stream failed: {e}")
            return {}

    # ── Working Memory 辅助操作 ─────────────────────────────
    def append_to_wm(self, item: str) -> None:
        """向工作记忆追加一条（尾部），超出 capacity 时截断头部。"""
        cap = 6  # 默认 4±2
        try:
            from .config import get_brain_config
            cap = max(2, int(get_brain_config().get("working_memory_capacity", 6)))
        except Exception:
            pass

        def _fn(stream):
            wm = stream.setdefault("working_memory", [])
            wm.append(item[:200])
            if len(wm) > cap:
                del wm[:len(wm) - cap]

        self.mutate_stream(_fn)

    def clear_working_memory(self) -> None:
        """清空工作记忆（Sleep Tick 时调用）。"""
        def _fn(stream):
            stream["working_memory"] = []
        self.mutate_stream(_fn)

    def replace_working_memory(self, items: list[str]) -> None:
        """替换整个工作记忆（Day Tick 时调用）。"""
        def _fn(stream):
            stream["working_memory"] = list(items)
        self.mutate_stream(_fn)

    # ── 便捷写（scheduler / session 用）────────────────────
    def mark_user_contact(self) -> None:
        """用户输入或主动联系发生时刷新 last_user_contact_at / idle_seconds。"""
        from main_brain.clock import now_iso
        self.update_life_node({
            "last_user_contact_at": now_iso(),
            "idle_seconds": 0,
        })

    def mark_proactive_contact(self) -> None:
        from main_brain.clock import now_iso
        self.update_life_node({"last_proactive_contact_at": now_iso()})

    def set_loop_status(self, status: str, *, activity: str = "",
                        focus: str = "") -> None:
        from main_brain.clock import now_iso
        delta = {"life_loop_status": status, "last_activity_at": now_iso()}
        if activity:
            delta["current_activity"] = activity
        if focus:
            delta["current_focus"] = focus
            delta.setdefault("focus_since", now_iso())
        self.update_life_node(delta)

    def set_error(self, msg: str) -> None:
        self.update_life_node({"last_error": (msg or "")[:300]})

    # ── judge state_updates 路由 ───────────────────────────
    def apply_state_updates(self, state_updates: dict) -> dict:
        """把 judge 的 state_updates 路由到 life 节点 / 现有 manager。

        Returns: 实际生效的 delta 摘要（供日志）。
        """
        if not isinstance(state_updates, dict) or not state_updates:
            return {}
        delta = {}
        # 1. life 节点标量字段
        node_delta = {k: v for k, v in state_updates.items() if k in _LIFE_NODE_FIELDS}
        if node_delta:
            self.update_life_node(node_delta)
            delta.update(node_delta)
        # 2. recent_thoughts（追加）
        for t in state_updates.get("recent_thoughts", []) or []:
            if isinstance(t, str):
                self.append_recent_thought(t)
            elif isinstance(t, dict):
                self.append_recent_thought(
                    t.get("summary", ""), focus=t.get("focus", ""), source="judge")
        # 3. open_loops → 现有 manager
        for loop in state_updates.get("open_loops", []) or []:
            if isinstance(loop, dict):
                try:
                    from main_brain.state import get_open_loops
                    get_open_loops().create(
                        loop.get("content", ""),
                        loop.get("node_ids", []) or [],
                    )
                    delta.setdefault("open_loops_created", []).append(loop.get("content", "")[:40])
                except Exception as e:
                    logger.warning(f"[state_adapter] open_loop create failed: {e}")
        # 4. working_set → 现有 manager
        for w in state_updates.get("working_set", []) or []:
            if isinstance(w, dict) and w.get("ref_id"):
                try:
                    from main_brain.state import get_working_set
                    get_working_set().upsert(
                        w.get("type", "node"), w["ref_id"],
                        score=float(w.get("score", 0.5)),
                        source=w.get("source", "brain_judge"),
                    )
                    delta.setdefault("working_set_upserted", []).append(w["ref_id"][:24])
                except Exception as e:
                    logger.warning(f"[state_adapter] working_set upsert failed: {e}")
        # 5. concerns 激活
        for c in state_updates.get("concerns", []) or []:
            if isinstance(c, dict) and c.get("node_id"):
                try:
                    from main_brain.state import get_concerns
                    get_concerns().activate(
                        c["node_id"], boost=float(c.get("boost", 0.15)))
                    delta.setdefault("concerns_activated", []).append(c["node_id"][:24])
                except Exception as e:
                    logger.warning(f"[state_adapter] concern activate failed: {e}")
        return delta

    # ── action_handler 约定 ─────────────────────────────────
    def handle_update_state(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                            dry_run: bool) -> dict:
        updates = decision.state_updates or {}
        if dry_run:
            return {"result_summary": f"[dry_run] update_state: {list(updates.keys())}"}
        delta = self.apply_state_updates(updates)
        keys = list(delta.keys())
        return {
            "result_summary": f"状态更新: {keys}" if keys else "状态更新(无变化)",
            "state_delta": {"source": "update_state", "delta": delta},
        }


_state_adapter: StateAdapter | None = None


def get_state_adapter() -> StateAdapter:
    global _state_adapter
    if _state_adapter is None:
        _state_adapter = StateAdapter()
    return _state_adapter
