"""
自我叙事管线步骤 — narrative_significance (store) + narrative_warmth (search)
"""
import logging
import threading

from main_brain.memory.pipeline.context import StepDef

from .store import get_self_narrative
from .prompts import NARRATIVE_SIGNIFICANCE_PROMPT
from .utils import parse_json

logger = logging.getLogger('main_brain.narrative_steps')


def _execute_significance(ctx) -> None:
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        return

    events = meta.get("_events", [])
    add_events = [e for e in events if e.get("event") == "ADD" and e.get("id")]
    if not add_events:
        return

    try:
        store = get_self_narrative()
        if not store:
            return
    except Exception:
        return

    chapter = store.get_current_chapter()
    chapter_title = chapter.get("title", "")

    def _bg_tag(events_list, ch_title):
        from main_brain.memory.llm import call_llm
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
                if parsed.get("is_core"):
                    store.enforce_core_budget()
            except Exception as e:
                logger.warning("[step:significance] failed for {}: {}".format(
                    ev.get("id", "?")[:8], e))

    threading.Thread(target=_bg_tag, args=(add_events, chapter_title), daemon=True).start()


def _make_significance_step():
    return StepDef(
        name="narrative_significance",
        description="叙事锚点标记 — 评估记忆的叙事价值",
        execute=_execute_significance,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=5.0,
    )


# ── Search 管线步骤: narrative_warmth ──────────────────────────


def _execute_warmth(ctx) -> None:
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        return

    memories = list(ctx.intermediate.get("semantic_results", []))
    event_results = ctx.intermediate.get("event_results")
    if event_results:
        memories.extend(event_results)
    graph_results = ctx.intermediate.get("graph_results")
    if graph_results:
        memories.extend(graph_results)

    if not memories:
        return

    try:
        store = get_self_narrative()
        if not store:
            return
    except Exception:
        return

    mem_ids = [m.get("id") for m in memories if m.get("id")]
    if not mem_ids:
        return

    anchors = store.get_anchors_for_memories(mem_ids)
    if not anchors:
        return

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
        min_activation = store.calculate_min_activation(anchor)
        if min_activation > 0 and m.get("score", 0) < min_activation:
            m["score"] = round(min_activation, 4)
            boosted += 1

    memories.sort(key=lambda x: x.get("score", 0), reverse=True)
    if boosted:
        logger.info("[step:warmth] boosted {} memories with narrative warmth".format(boosted))


def _make_warmth_step():
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
    engine.register_step(_make_significance_step())
    engine.register_step(_make_warmth_step())
    logger.info("[pipeline] narrative steps registered")
