"""
反思引擎 — 对话后自动反思，更新自传文档和叙事锚点

流程：
1. 获取当前自传
2. LLM 分析对话内容
3. 更新自传文档
4. 标记叙事锚点
5. 执行身份预算
"""
import logging
from datetime import datetime

logger = logging.getLogger('self_narrative')

# 总文本长度低于此阈值时跳过反思（避免无意义的 LLM 调用）
_MIN_TOTAL_LENGTH = 30


def reflect_on_conversation(store, user_msg: str, assistant_msg: str):
    """对话后反思主流程

    Args:
        store: SelfNarrativeStore 实例
        user_msg: 用户消息
        assistant_msg: AI 回复
    """
    if not user_msg or not assistant_msg:
        return

    # 简单消息跳过反思：总长度太短
    total_len = len(user_msg.strip()) + len(assistant_msg.strip())
    if total_len < _MIN_TOTAL_LENGTH:
        logger.info("[reflection] skip short conversation")
        return

    logger.info("[reflection] start reflection on conversation")
    try:
        # 1. 获取当前自传（只读一次，后续复用）
        autobiography = store.get_autobiography()

        # 2. LLM 分析
        reflection_result = _call_reflection_llm(user_msg, assistant_msg, autobiography)
        if not reflection_result:
            logger.warning("[reflection] LLM analysis failed, skip")
            return

        # 3. 更新自传（如果 LLM 建议更新）
        if reflection_result.get("should_update_narrative"):
            _apply_narrative_updates(store, autobiography, reflection_result)

        # 4. 更新对话计数和反思时间
        #    直接在内存中的 autobiography 对象上操作，避免再次读磁盘
        current = autobiography.get("current_state", {})
        current["conversation_count"] = current.get("conversation_count", 0) + 1
        current["last_reflection_at"] = datetime.utcnow().isoformat()

        # 如果 LLM 给出了 current_state 更新则合并
        state_update = reflection_result.get("narrative_updates", {}).get("current_state", {})
        if state_update:
            current.update(state_update)

        store.update_current_state(**current)

        # 5. 标记叙事锚点
        memory_significance = reflection_result.get("memory_significance", [])
        if memory_significance:
            _tag_significant_memories(store, memory_significance)

        # 6. 执行身份预算
        store.enforce_core_budget()

        logger.info("[reflection] reflection completed")

    except Exception as e:
        logger.warning(f"[reflection] failed: {e}")


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
    result.setdefault("narrative_updates", {})
    result.setdefault("memory_significance", [])

    return result


def _apply_narrative_updates(store, autobiography: dict, reflection: dict):
    """将反思结果应用到自传文档"""
    updates = reflection.get("narrative_updates", {})
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

    # 新增章节（兼容字符串和字典两种格式）
    new_chapter = updates.get("new_chapter")
    if new_chapter:
        if isinstance(new_chapter, str):
            new_chapter = {"title": new_chapter, "summary": new_chapter}
        if isinstance(new_chapter, dict):
            chapters = autobiography.get("life_story", {}).get("chapters", [])
            chapters.append({
                "title": new_chapter.get("title", "未命名章节"),
                "period": new_chapter.get("period", datetime.utcnow().strftime("%Y-%m")),
                "summary": new_chapter.get("summary", ""),
                "key_memories": [],
                "lessons": [],
            })
        autobiography.setdefault("life_story", {})["chapters"] = chapters
        autobiography["life_story"]["current_chapter_index"] = len(chapters) - 1
        changed = True

    # 新增里程碑（兼容字符串和字典两种格式）
    milestone = updates.get("milestone")
    if milestone:
        if isinstance(milestone, str):
            milestone = {"title": milestone, "description": milestone}
        if isinstance(milestone, dict):
            milestones = autobiography.get("milestones", [])
            milestone.setdefault("added_at", datetime.utcnow().isoformat())
            milestone.setdefault("title", "未命名里程碑")
            milestones.append(milestone)
            autobiography["milestones"] = milestones
            changed = True

    # 新增教训/感悟
    lessons = updates.get("lessons")
    if lessons and isinstance(lessons, list):
        chapter = autobiography.get("life_story", {}).get("chapters", [])
        idx = autobiography.get("life_story", {}).get("current_chapter_index", 0)
        if chapter and 0 <= idx < len(chapter):
            chapter_lessons = chapter[idx].get("lessons", [])
            chapter_lessons.extend(lessons)
            chapter[idx]["lessons"] = chapter_lessons
            changed = True

    if changed:
        store.update_autobiography(autobiography)
        logger.info(f"[reflection] autobiography updated | milestone={bool(milestone)} chapter={bool(new_chapter)}")


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
