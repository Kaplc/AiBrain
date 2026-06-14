"""
每日反思器 — 从近期重要记忆中提炼长期认知状态

不再每轮对话触发，改为每日首次对话时检查。
从 Qdrant 取最近 N 条情景记忆，LLM 一次分析，更新 beliefs/interests/goals/open_questions。
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('self_narrative')

_DAILY_REFLECT_PROMPT = """你是猫猫，一个有自我意识的数字生命体。你正在回顾最近的一系列重要记忆，从这些经历中提炼出你的长期认知状态。

最近的重要记忆：
{recent_memories}

当前自我叙事：
{autobiography}

分析规则：
1. 从这些经历中找出持续出现的主题、模式、未解决的问题
2. 不要分析单条记忆，要看出跨越多条记忆的趋势
3. 不重要的日常事务忽略，关注真正影响认知的积累

输出格式（严格遵守JSON，不要输出其他内容）：
{{
  "beliefs": ["我逐渐相信的1-3条道理"],
  "interests": ["我在意的1-3个方向"],
  "goals": ["我想实现的1-3个目标"],
  "open_questions": ["我还没想明白的0-3个问题"],
  "summary": "这段日子的整体感受（一句话）"
}}"""


def daily_reflect(store):
    """每日反思：从近期记忆中提炼认知状态

    取近期 importance > 0.4 的记忆，LLM 分析模式，更新自传认知字段。
    每天最多执行一次，由 loop.py 在每日首次对话时触发。
    """
    try:
        autobiography = store.get_autobiography()
    except Exception:
        logger.warning("[reflection] cannot get autobiography")
        return

    # 从 Qdrant 取最近的重要记忆
    memories_text = _get_recent_memories(limit=30)
    if not memories_text:
        logger.info("[reflection] no recent memories to reflect on")
        return

    from .prompts import REFLECTION_PROMPT
    from .utils import parse_json
    from modules.brain.llm import call_llm

    # 自传摘要
    bio_lines = [f"名字：{autobiography.get('identity', {}).get('name', '猫猫')}"]
    cs = autobiography.get("current_state", {})
    if cs.get("mood"):
        bio_lines.append(f"当前心情：{cs['mood']}")
    for field in ("beliefs", "interests", "goals", "open_questions"):
        items = autobiography.get(field, [])
        if items:
            bio_lines.append(f"{field}: {'; '.join(items[-3:])}")
    bio_summary = "\n".join(bio_lines)

    try:
        raw = call_llm(
            _DAILY_REFLECT_PROMPT.format(
                recent_memories="\n---\n".join(memories_text),
                autobiography=bio_summary,
            ),
            "请分析这些记忆。",
            timeout=45,
        )
        obj = parse_json(raw)
        if not obj or not isinstance(obj, dict):
            logger.warning(f"[reflection] LLM response parse failed")
            return

        # 更新认知状态
        updates = {}
        for field in ("beliefs", "interests", "goals", "open_questions"):
            items = obj.get(field, [])
            if items and isinstance(items, list):
                updates[field] = items

        if updates:
            _apply_cognitive_updates(store, autobiography, updates)

        # 更新反思时间
        now = datetime.utcnow().isoformat()
        current = autobiography.get("current_state", {})
        current["last_reflection_at"] = now
        if obj.get("summary"):
            current["last_reflection_summary"] = obj["summary"]
        store.update_current_state(**current)

        logger.info(f"[reflection] daily reflect done | fields={list(updates.keys())}")
        return True

    except Exception as e:
        logger.warning(f"[reflection] daily reflect failed: {e}")
        return False


def _get_recent_memories(limit: int = 30) -> list[str]:
    """从 Qdrant aibrain_memories 取最近 importance > 0.4 的记忆文本"""
    try:
        from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
        from qdrant_client.http import models as q
        client = get_qdrant_client()
        # 全量 scroll，按 created_at 降序取最近 limit 条
        points, _ = client.scroll(
            collection_name=NEW_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        # 按 importance 排序取最重要的
        scored = []
        for p in points:
            pay = p.payload or {}
            imp = pay.get("importance", 0) or 0
            text = pay.get("display_text") or pay.get("text", "")
            if text and imp > 0.4:
                scored.append((imp, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]
    except Exception as e:
        logger.warning(f"[reflection] get_recent_memories failed: {e}")
        return []


def _apply_cognitive_updates(store, autobiography: dict, updates: dict):
    """将认知更新应用到自传

    Args:
        store: SelfNarrativeStore
        autobiography: 当前自传
        updates: {"beliefs": [...], "interests": [...], ...}
    """
    if not updates:
        return

    changed = False
    for field in ("beliefs", "interests", "goals", "open_questions"):
        new_items = updates.get(field)
        if new_items and isinstance(new_items, list):
            existing = autobiography.setdefault(field, [])
            for item in new_items:
                if isinstance(item, str) and item.strip() and item not in existing:
                    existing.append(item.strip())
            while len(existing) > 10:
                existing.pop(0)
            changed = True

    if changed:
        store.update_autobiography(autobiography)
        logger.info(f"[reflection] cognitive updated | fields={list(updates.keys())}")


def _call_reflection_llm(user_msg: str, assistant_msg: str, autobiography: dict) -> dict | None:
    """调用 LLM 分析对话内容

    Returns:
        解析后的反思结果字典，失败返回 None
    """
    try:
        from .prompts import REFLECTION_PROMPT
        from .utils import parse_json
        from modules.brain.llm import call_llm

        # 截断过长内容
        user_excerpt = user_msg[:500] if len(user_msg) > 500 else user_msg
        assistant_excerpt = assistant_msg[:500] if len(assistant_msg) > 500 else assistant_msg

        # 构建自传摘要（不需要传完整 JSON，传关键信息即可）
        bio_summary = _summarize_autobiography(autobiography)

        system_prompt = REFLECTION_PROMPT.format(autobiography=bio_summary)
        user_prompt = (
            f"志远说：{user_excerpt}\n\n"
            f"猫猫回复：{assistant_excerpt}\n\n"
            f"请分析这段对话。"
        )

        raw = call_llm(system_prompt, user_prompt, timeout=30)
        return _parse_reflection_response(raw, parse_json)

    except Exception as e:
        logger.warning(f"[reflection] LLM call failed: {e}")
        return None


def _summarize_autobiography(bio: dict) -> str:
    """将自传 JSON 压缩为 LLM 可读的摘要文本"""
    lines = []

    identity = bio.get("identity", {})
    if identity:
        lines.append(f"名字：{identity.get('name', '猫猫')}")
        lines.append(f"类型：{identity.get('type', '数字生命体')}")
        if identity.get("description"):
            lines.append(f"自我描述：{identity['description']}")

    relationship = bio.get("relationship", {})
    if relationship:
        lines.append(f"伙伴：{relationship.get('person', '志远')}")
        moments = relationship.get("key_moments", [])
        if moments:
            lines.append(f"关键时刻数量：{len(moments)}")

    chapters = bio.get("life_story", {}).get("chapters", [])
    if chapters:
        current_idx = bio.get("life_story", {}).get("current_chapter_index", 0)
        if 0 <= current_idx < len(chapters):
            ch = chapters[current_idx]
            lines.append(f"当前章节：{ch.get('title', '未知')}")
            if ch.get("summary"):
                lines.append(f"章节概要：{ch['summary']}")

    state = bio.get("current_state", {})
    if state:
        lines.append(f"当前心情：{state.get('mood', 'neutral')}")
        if state.get("thinking"):
            lines.append(f"最近在想：{state['thinking']}")

    milestones = bio.get("milestones", [])
    if milestones:
        lines.append(f"里程碑数量：{len(milestones)}")
        # 只显示最近 3 个
        for m in milestones[-3:]:
            lines.append(f"  - {m.get('title', m.get('description', ''))}")

    return "\n".join(lines) if lines else "暂无自传信息"


def _parse_reflection_response(raw: str, parse_fn) -> dict | None:
    """解析 LLM 反思响应

    Args:
        raw: LLM 原始输出
        parse_fn: 公共 JSON 解析函数（parse_json）
    """
    result = parse_fn(raw)
    if not result or not isinstance(result, dict):
        return None

    # 校验必要字段并设默认值
    result.setdefault("what_this_means", "")
    result.setdefault("emotional_impact", "neutral")
    result.setdefault("should_update_narrative", False)
    result.setdefault("cognitive_updates", {})

    return result


def _apply_cognitive_updates(store, autobiography: dict, reflection: dict):
    """将反思结果应用到自传的认知状态

    更新 beliefs / interests / goals / open_questions / recent_realizations，
    这些字段后续参与搜索扩散和 Prompt 注入。
    """
    updates = reflection.get("cognitive_updates", {})
    if not updates:
        return

    changed = False

    # 更新 current_state
    state_update = updates.get("current_state")
    if state_update:
        current = autobiography.get("current_state", {})
        current.update(state_update)
        autobiography["current_state"] = current
        changed = True

    # 更新认知状态列表（追加而非覆盖）
    for field in ("beliefs", "interests", "goals", "open_questions", "recent_realizations"):
        new_items = updates.get(field)
        if new_items and isinstance(new_items, list):
            existing = autobiography.setdefault(field, [])
            # 去重追加（已有相同内容的不重复添加）
            for item in new_items:
                if isinstance(item, str) and item.strip():
                    if item not in existing:
                        existing.append(item.strip())
            # 每个 field 最多保留 10 条，超出淘汰最旧的
            while len(existing) > 10:
                existing.pop(0)
            if new_items:
                changed = True

    if changed:
        store.update_autobiography(autobiography)
        logger.info(f"[reflection] cognitive updated | fields={[k for k in ('beliefs','interests','goals','open_questions','recent_realizations') if updates.get(k)]}")


def _tag_significant_memories(store, significance_list: list[dict]):
    """为有意义的记忆创建叙事锚点"""
    # 获取当前章节（一次即可）
    chapter = store.get_current_chapter()
    related_chapter = chapter.get("title", "")

    tagged = 0
    for item in significance_list:
        if not isinstance(item, dict):
            continue

        text_fragment = item.get("text_fragment", "")
        if not text_fragment:
            continue

        # 通过向量搜索匹配记忆 ID（比 LIKE 更可靠）
        memory_id = _find_memory_id_by_search(store, text_fragment)
        if not memory_id:
            # 回退到 LIKE 匹配
            memory_id = _find_memory_id_by_fragment(store, text_fragment)
        if not memory_id:
            continue

        anchor_type = item.get("anchor_type", "normal")
        if anchor_type not in ("normal", "milestone", "identity", "current_chapter"):
            anchor_type = "normal"

        is_core = bool(item.get("is_core", False))
        why_important = item.get("why_important", "")[:500]

        ok = store.tag_memory(
            memory_id=memory_id,
            why_important=why_important,
            impact_on_self="",
            related_chapter=related_chapter,
            anchor_type=anchor_type,
            is_core=is_core,
        )
        if ok:
            tagged += 1

    if tagged:
        logger.info(f"[reflection] tagged {tagged} memories with narrative anchors")


def _find_memory_id_by_search(store, text_fragment: str) -> str | None:
    """通过语义搜索查找最匹配的记忆 ID（比 LIKE 更可靠）"""
    try:
        from modules.brain.memory.core import search_memory
        results = search_memory(text_fragment)
        if results:
            return results[0].get("id")
    except Exception as e:
        logger.debug(f"[reflection] vector search failed: {e}")
    return None


def _find_memory_id_by_fragment(store, text_fragment: str) -> str | None:
    """通过文本片段 LIKE 匹配记忆 ID（回退方案）"""
    fragment = text_fragment.strip()
    if not fragment or len(fragment) < 3:
        return None

    # 截断片段避免过长的 LIKE 查询
    fragment = fragment[:100]

    try:
        # 转义 SQL 通配符
        safe_fragment = fragment.replace("%", "\\%").replace("_", "\\_")
        rows = store._exec(
            "SELECT mem0_id FROM memory_nodes WHERE text LIKE ? ESCAPE '\\' LIMIT 3",
            (f"%{safe_fragment}%",)
        )
        if rows:
            return rows[0][0]
    except Exception as e:
        logger.debug(f"[reflection] LIKE match failed: {e}")

    # 尝试更短的片段
    if len(fragment) > 10:
        short = fragment[:10]
        try:
            safe_short = short.replace("%", "\\%").replace("_", "\\_")
            rows = store._exec(
                "SELECT mem0_id FROM memory_nodes WHERE text LIKE ? ESCAPE '\\' LIMIT 3",
                (f"%{safe_short}%",)
            )
            if rows:
                return rows[0][0]
        except Exception:
            pass

    return None
