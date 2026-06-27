"""复习已学知识（review）— 主动回顾 self_learn 沉淀的内容

流程:
  搜索自学习记忆 → 筛选 source=self_learn → 选最近 / 最高分
  → 激活 concern → 记录复习事件

在 daemon medium_tick 中作为可选活动执行，让 brain 定期"想起"学过的内容。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("self_learn.review")


def run_review(tick_input, dry_run: bool = False) -> dict:
    """执行一次知识复习。

    搜索自学习记忆，选出最相关的一条，将其话题重新激活为兴趣点，
    使 brain 保持对已学知识的关注。

    Args:
        tick_input: TickInput 兼容 dict 或 dataclass
        dry_run: 为 True 时仅返回即将复习的话题，不修改状态

    Returns:
        dict: {ok, skipped, reason, topic, memory_id}
    """
    from main_brain.memory.core import search_memory

    if dry_run:
        return {"ok": True, "dry_run": True}

    # 1. 搜索记忆（用语义相关的 query + boost 机制召回自学习记忆）
    memories = search_memory("最近学到的知识")

    # 2. 筛选 source=self_learn 的记忆
    learned = []
    for m in memories:
        if m.get("payload", {}).get("source") == "self_learn":
            learned.append(m)

    if not learned:
        logger.info("[review] 无自学习记忆待复习")
        return {"ok": False, "skipped": True, "reason": "no_learned_items"}

    # 3. 按 score 排序，选最高分
    learned.sort(key=lambda x: x.get("score", 0), reverse=True)
    target = learned[0]

    topic = target.get("payload", {}).get("topic", "") or target.get("text", "")[:80]
    memory_id = target.get("id", "")

    # 4. 激活 concern（低 boost，仅是"想起来"）
    try:
        from main_brain.state import get_concerns
        get_concerns().activate(topic, boost=0.15)
        logger.info(f"[review] 激活 concern: {topic[:40]} (mem={memory_id[:12]})")
    except Exception as e:
        logger.warning(f"[review] activate concern failed: {e}")

    return {
        "ok": True,
        "topic": topic,
        "memory_id": memory_id,
        "score": target.get("score", 0),
    }
