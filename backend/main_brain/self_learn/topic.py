"""话题选择 — 缺口优先 + 好奇心兜底

缺口话题：
  - 从 open_loops 中选 tension() 最高的 loop
  - 直接用其 content 作为话题,无需 LLM

好奇心话题（兜底）：
  - 从 goals / recent_thoughts / concerns 中随机选一个作为种子话题
  - MVP 暂不调 LLM，直接从 goals 的 name/description 提取
"""
from __future__ import annotations

import logging
import random

logger = logging.getLogger("self_learn.topic")


def select_topic(life_state: dict) -> tuple:
    """选择学习话题。

    Returns:
        (topic: str, source: str, loop_id: str | None)
        source = "gap" | "curiosity"
        若无合适话题返回 ("", "", None)
    """
    # 第 1 步：缺口优先 — 从 open_loops 选
    open_loops = life_state.get("open_loops", []) or []
    if open_loops:
        try:
            from main_brain.state.open_loops import OpenLoopManager
            mgr = OpenLoopManager()
            ranked = sorted(
                [l for l in open_loops if isinstance(l, dict) and l.get("status") in ("open", None)],
                key=lambda l: _tension_or_zero(l, mgr),
                reverse=True,
            )
            if ranked:
                top = ranked[0]
                content = (top.get("content", "") or "").strip()
                if content:
                    return (content, "gap", top.get("id"))

                # 无 content 时用第一个节点名代替
                node_ids = top.get("node_ids", []) or []
                if node_ids:
                    return (str(node_ids[0]), "gap", top.get("id"))
        except Exception as e:
            logger.warning(f"[topic] gap selection failed: {e}")

    # 第 2 步：好奇心兜底 — 从 goals/recent_thoughts 选
    goals = life_state.get("goals", []) or []
    if goals:
        for g in goals:
            if isinstance(g, dict):
                name = g.get("name", "") or ""
                desc = g.get("description", "") or ""
                candidate = name or desc
                if candidate:
                    return (candidate[:200], "curiosity", None)

    # 从 recent_thoughts 中选最近一条
    thoughts = life_state.get("recent_thoughts", []) or []
    for t in reversed(thoughts):
        summary = ""
        if isinstance(t, dict):
            summary = t.get("summary", "") or ""
        elif isinstance(t, str):
            summary = t
        if summary and len(summary) > 10:
            return (summary[:200], "curiosity", None)

    return ("", "", None)


def _tension_or_zero(loop: dict, mgr) -> float:
    try:
        return mgr.tension(loop)
    except Exception:
        return 0.0
