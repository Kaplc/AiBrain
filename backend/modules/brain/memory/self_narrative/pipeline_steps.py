"""
自我叙事管线步骤 — narrative_significance (store) + narrative_warmth (search)

narrative_significance: 在记忆存储后，用 LLM 判断是否叙事相关并创建锚点
narrative_warmth: 在搜索结果中，为叙事锚点记忆额外加分和保护
"""
import logging
import threading

logger = logging.getLogger('self_narrative.pipeline')

# ── Store 管线步骤: narrative_significance ─────────────────────


def _execute_significance(ctx) -> None:
    """执行叙事显著性判断：对新增记忆评估叙事价值并标记锚点

    读取 ctx.metadata["_events"] 中的 ADD 事件。
    失败不影响管线继续。
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        return

    events = meta.get("_events", [])
    add_events = [e for e in events if e.get("event") == "ADD" and e.get("id")]
    if not add_events:
        return

    # 获取 SelfNarrativeStore
    try:
        from . import get_self_narrative
        store = get_self_narrative()
        if not store:
            return
    except Exception:
        return

    # 获取当前章节
    chapter = store.get_current_chapter()
    chapter_title = chapter.get("title", "")

    def _bg_tag(events_list, ch_title):
        """后台线程：逐条评估叙事显著性"""
        from .prompts import NARRATIVE_SIGNIFICANCE_PROMPT
        from .utils import parse_json
        from modules.brain.llm import call_llm

        for ev in events_list:
            try:
                mem_text = ev.get("memory", "")
                if not mem_text or len(mem_text.strip()) < 5:
                    continue

                raw = call_llm(NARRATIVE_SIGNIFICANCE_PROMPT, f"记忆文本：{mem_text}", timeout=15)
                parsed = parse_json(raw)
                if not parsed or not parsed.get("is_significant"):
                    continue

                store.tag_memory(
                    memory_id=ev["id"],
                    why_important=parsed.get("why_important", ""),
                    impact_on_self=parsed.get("impact_on_self", ""),
                    related_chapter=ch_title,
                    anchor_type=parsed.get("anchor_type", "normal"),
                    is_core=bool(parsed.get("is_core", False)),
                )

                # 核心记忆检查预算
                if parsed.get("is_core"):
                    store.enforce_core_budget()

            except Exception as e:
                logger.warning(f"[step:significance] failed for {ev.get('id', '?')[:8]}: {e}")

    # 后台线程执行，不阻塞管线
    threading.Thread(target=_bg_tag, args=(add_events, chapter_title), daemon=True).start()


def _make_significance_step():
    """创建 narrative_significance StepDef"""
    from ..pipeline.context import StepDef
    return StepDef(
        name="narrative_significance",
        description="叙事锚点标记 — 评估记忆的叙事价值",
        execute=_execute_significance,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=5.0,  # 只启动线程，本身很快
    )


# ── Search 管线步骤: narrative_warmth ──────────────────────────


def _execute_warmth(ctx) -> None:
    """执行叙事温度加成：为有叙事锚点的搜索结果加分并设最低激活值

    从 ctx.intermediate 中收集所有搜索结果，查询锚点，修改 score。
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        return

    # 收集所有搜索结果
    memories = list(ctx.intermediate.get("semantic_results", []))
    event_results = ctx.intermediate.get("event_results")
    if event_results:
        memories.extend(event_results)
    graph_results = ctx.intermediate.get("graph_results")
    if graph_results:
        memories.extend(graph_results)

    if not memories:
        return

    # 获取 SelfNarrativeStore
    try:
        from . import get_self_narrative
        store = get_self_narrative()
        if not store:
            return
    except Exception:
        return

    # 收集所有 memory_id
    mem_ids = [m.get("id") for m in memories if m.get("id")]
    if not mem_ids:
        return

    # 批量查询锚点
    anchors = store.get_anchors_for_memories(mem_ids)
    if not anchors:
        return

    # 应用温度加成和最低激活值
    boosted = 0
    for m in memories:
        mid = m.get("id", "")
        anchor = anchors.get(mid)
        if not anchor:
            continue

        warmth = anchor.get("warmth_boost", 0.0)
        if warmth > 0:
            m["score"] = round(min(1.0, m.get("score", 0.5) + warmth), 4)
            boosted += 1

        # 设定最低激活值
        min_activation = store.calculate_min_activation(anchor)
        if min_activation > 0 and m.get("score", 0) < min_activation:
            m["score"] = round(min_activation, 4)
            boosted += 1

    # 重新排序
    memories.sort(key=lambda x: x.get("score", 0), reverse=True)

    if boosted:
        logger.info(f"[step:warmth] boosted {boosted} memories with narrative warmth")


def _make_warmth_step():
    """创建 narrative_warmth StepDef"""
    from ..pipeline.context import StepDef
    return StepDef(
        name="narrative_warmth",
        description="叙事温度加成 — 为叙事锚点记忆加分",
        execute=_execute_warmth,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=10.0,
    )


# ── 注册函数 ────────────────────────────────────────────────────


def register_narrative_steps(engine):
    """注册自我叙事管线步骤到引擎

    Args:
        engine: PipelineEngine 实例
    """
    engine.register_step(_make_significance_step())
    engine.register_step(_make_warmth_step())
    logger.info("[pipeline] narrative steps registered (narrative_significance + narrative_warmth)")
