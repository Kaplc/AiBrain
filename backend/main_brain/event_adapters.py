"""事件适配器 — 绑定 Brai nEvent 到 state/memory/learning 副作用（T006 / FR-006）

每个适配器是一个 router 可注册的 EventHandler，专注于单一副作用：
  - state_event_adapter:  更新 life_state focus / activity
  - memory_event_adapter: 事件触发的记忆召回（已有，在 orchestrator._recall_memory 中）
  - learning_event_adapter: 从工具结果中提取学习线索

注册方式：from .router import register; register(source, type, handler)
"""
from __future__ import annotations

import logging

from .contracts import (
    BrainEvent, BrainCycleContext,
    EVENT_SOURCE_CHAT, EVENT_SOURCE_TOOL, EVENT_SOURCE_TICK,
    EVENT_TYPE_USER_MESSAGE, EVENT_TYPE_TOOL_RESULT, EVENT_TYPE_TICK,
)

logger = logging.getLogger("main_brain.event_adapters")


# ── 状态适配器 ───────────────────────────────────────────────

def state_event_adapter(event: BrainEvent, ctx: BrainCycleContext) -> dict | None:
    """状态更新适配器：根据事件内容更新 life_state。

    注册 source=chat type=user_message 和 source=tool。
    """
    if not event.content:
        return None

    try:
        from .adapters.state import get_state_adapter
        st = get_state_adapter()

        updates = {}
        if event.source == EVENT_SOURCE_CHAT:
            updates["current_focus"] = event.content[:60]
            updates["last_user_contact_at"] = _now_iso()
            st.mark_user_contact()
        elif event.source == EVENT_SOURCE_TOOL:
            tool_name = event.metadata.get("tool_name", "unknown")
            updates["current_focus"] = f"工具结果: {tool_name}"
        elif event.source == EVENT_SOURCE_TICK:
            tick_type = event.metadata.get("tick_type", "")
            updates["current_activity"] = tick_type

        if updates:
            st.update_life_node(updates)
            return {"state_updated": True, "updates": updates}

    except Exception as e:
        logger.debug(f"[state_adapter] update skipped: {e}")

    return None


# ── 学习适配器 ───────────────────────────────────────────────

def learning_event_adapter(event: BrainEvent, ctx: BrainCycleContext) -> dict | None:
    """学习适配器：从工具结果中沉淀学习线索。

    注册 source=tool type=tool_result。
    """
    if event.source != EVENT_SOURCE_TOOL:
        return None
    if not event.content:
        return None

    try:
        from .adapters.learning import get_learning_adapter
        learn = get_learning_adapter()

        hint = f"[事件学习] {event.metadata.get('tool_name', 'tool')} 执行结果: {event.content[:120]}"
        learn.sink_hints(
            hints=[hint],
            thought=f"tool_result event: {event.id[:12]}",
            focus=event.content[:40],
            source="event_orchestrator",
        )
        return {"learning_sunk": True}
    except Exception as e:
        logger.debug(f"[learning_adapter] sink skipped: {e}")

    return None


# ── 注册所有事件适配器 ──────────────────────────────────────

def register_event_adapters() -> None:
    """将所有事件适配器注册到 router。"""
    from .router import register

    # 状态适配器
    register(EVENT_SOURCE_CHAT, EVENT_TYPE_USER_MESSAGE, state_event_adapter)
    register(EVENT_SOURCE_TOOL, EVENT_TYPE_TOOL_RESULT, state_event_adapter)
    register(EVENT_SOURCE_TICK, EVENT_TYPE_TICK, state_event_adapter)

    # 学习适配器
    register(EVENT_SOURCE_TOOL, EVENT_TYPE_TOOL_RESULT, learning_event_adapter)

    logger.info("[event_adapters] registered: state + learning")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
