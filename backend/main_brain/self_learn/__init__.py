"""自主学习子包（self_learn）

编排入口: run_self_learn(tick_input, dry_run) -> dict

流程:
  guard(开关/每日上限/超时) → select_topic → cooldown 检查
  → search_and_digest → store_memory → 反馈(缺口add_thought / 冷却record / sink_hints)
"""
from __future__ import annotations

import hashlib
import logging

from .topic import select_topic
from .digest import search_and_digest

logger = logging.getLogger("self_learn")

# 兼容 TickInput: 可以是 TickInput dataclass 或纯 dict
_TICK_FIELDS = ("life_state", "tool_context", "recent_runs", "tick_type")


def run_self_learn(tick_input, dry_run: bool = False) -> dict:
    """执行一次自主学习节拍。"""
    from main_brain.config import get_brain_config
    cfg = get_brain_config()

    # 解包输入
    if hasattr(tick_input, "life_state"):
        life_state = tick_input.life_state
    elif isinstance(tick_input, dict):
        life_state = tick_input.get("life_state", {})
    else:
        life_state = {}

    # 1. Guard：总开关
    if not cfg.get("self_learn_enabled", True):
        return {"ok": False, "skipped": True, "reason": "self_learn_disabled"}

    # 1b. Guard：单日上限
    if _today_count() >= int(cfg.get("self_learn_max_per_day", 3)):
        return {"ok": False, "skipped": True, "reason": "max_per_day_reached"}

    # 2. 选话题
    topic, source, loop_id = select_topic(life_state)
    if not topic:
        return {"ok": False, "skipped": True, "reason": "no_topic"}

    # 3. Cooldown 检查（同一 topic 短时间内不重复学）
    topic_hash = hashlib.md5(topic.encode()).hexdigest()[:12]
    try:
        from main_brain.state import get_expression_history
        if get_expression_history().is_in_refractory("self_learn", topic_hash):
            return {"ok": False, "skipped": True, "reason": "topic_in_cooldown"}
    except Exception:
        pass

    if dry_run:
        return {"ok": True, "dry_run": True, "topic": topic, "source": source,
                "loop_id": loop_id, "cooldown_key": topic_hash}

    logger.info(f"[self_learn] topic={topic[:40]} source={source} loop_id={loop_id}")

    # 4. 搜索 + 提炼
    max_chars = int(cfg.get("self_learn_max_chars_per_topic", 3000))
    summary = search_and_digest(topic, max_chars=max_chars)
    if not summary:
        # 空摘要时用 topic 本身作为记忆内容
        summary = f"关于「{topic}」"

    # 5. 沉淀到情景记忆
    stored = ""
    try:
        from main_brain.memory.core import store_memory
        result = store_memory(summary, memory_meta={
            "source": "self_learn",
            "topic": topic,
            "topic_source": source,
            "loop_id": loop_id or "",
        })
        if isinstance(result, dict):
            added = result.get("added_count", 0)
            stored = f"ok+{added}" if added else result.get("result", "")[:16]
        else:
            stored = str(result)[:24]
    except Exception as e:
        logger.warning(f"[self_learn] store_memory failed: {e}")

    # 6a. 缺口话题反馈：add_thought
    if source == "gap" and loop_id:
        try:
            from main_brain.state.open_loops import OpenLoopManager
            OpenLoopManager().add_thought(loop_id)
        except Exception as e:
            logger.warning(f"[self_learn] add_thought failed: {e}")

    # 6b. 防重复冷却
    cooldown_hours = float(cfg.get("self_learn_cooldown_hours", 12))
    try:
        get_expression_history().record("self_learn", topic_hash, hours=cooldown_hours)
    except Exception as e:
        logger.warning(f"[self_learn] record cooldown failed: {e}")

    # 6c. 学习摘要入 recent_thoughts
    try:
        from main_brain.adapters.learning import get_learning_adapter
        summary_short = summary[:120] if summary else ""
        get_learning_adapter().sink_hints(
            [f"[self_learn] {topic}: {summary_short}"],
            source="self_learn",
        )
    except Exception as e:
        logger.warning(f"[self_learn] sink_hints failed: {e}")

    # 6d. 将话题激活为兴趣点（concern），使 brain 在意刚学的内容
    try:
        from main_brain.state import get_concerns
        get_concerns().activate(topic, boost=0.3)
        if source == "gap" and loop_id:
            get_concerns().activate(loop_id[:40], boost=0.2)
    except Exception as e:
        logger.warning(f"[self_learn] activate concern failed: {e}")

    logger.info(f"[self_learn] done topic={topic[:30]} stored={stored}")
    return {
        "ok": True,
        "topic": topic,
        "source": source,
        "loop_id": loop_id,
        "stored": stored,
        "summary_len": len(summary),
    }


def _today_count() -> int:
    """查询今日已执行 self_learn 的次数（扫 expression_history）。"""
    try:
        from main_brain import clock as times
        from main_brain.state import get_expression_history
        try:
            mgr = get_expression_history()
            state = mgr._state.snapshot()
        except Exception:
            state = {}
        today = times.now_iso()[:10]  # YYYY-MM-DD
        count = 0
        for h in state.get("expression_history", []):
            if h.get("expression_type") == "self_learn":
                last = h.get("last_expressed", "")
                if last[:10] == today:
                    count += 1
        return count
    except Exception:
        return 0
