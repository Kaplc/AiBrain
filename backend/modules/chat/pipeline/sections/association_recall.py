"""联想触发器 — 对话开始时按话题实体召回历史关联记忆，注入【背景关联】

流程：抽取话题实体 → 查共现实体（图 SQL）→ 召回相关记忆（图 SQL）→ 注入 prompt。
用图 SQL 召回而非 search_memory，避免每轮 N 次完整搜索管线的延迟。
全包 try/except 静默降级，慢/失败绝不阻断对话。
"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    """从语义搜索结果拿实体 → 查共现 → 召回关联记忆 → 注入 prompt

    不再额外调 LLM 抽实体，直接用语义搜索回来的记忆里的实体名，
    与 graph 表里存的实体天然一致，没有中英文不匹配的问题。
    """

    # 1. 取语义搜索结果（memory section 也在用同一份数据）
    pkg = ctx.work_memory.get("package", {})
    results = pkg.get("results", [])
    if not results:
        return

    try:
        from modules.brain.graph import get_graph
    except Exception:
        return

    graph = get_graph()
    if graph is None:
        return

    # 2. 从语义结果中收集实体（去重）
    mem_ids = [r.get("id") for r in results if r.get("id")]
    if not mem_ids:
        return

    entity_map = graph.get_entities_for_memories(mem_ids)
    all_ents = []
    for mid in mem_ids:
        all_ents.extend(entity_map.get(mid, []))
    all_ents = list(dict.fromkeys(all_ents))
    if not all_ents:
        return

    # 3. 查共现关联实体（纯 SQL，图路径）
    related = graph.get_related_entities(all_ents, top_k=5)
    if not related:
        return

    # 4. 召回关联实体相关的记忆
    related_entity_names = [e for e, _ in related[:3]]
    related_mem_ids = graph.get_related_memories(related_entity_names, top_k=5)
    if not related_mem_ids:
        return

    # 从 Qdrant 取 display_text（图不再存文本）
    try:
        from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION
        client = get_qdrant_client()
        points = client.retrieve(collection_name=NEW_COLLECTION, ids=related_mem_ids)
    except Exception:
        return
    mem_lines = []
    for p in points:
        pay = p.payload or {}
        text = pay.get("display_text") or pay.get("text", "")
        if not text:
            continue
        raw = pay.get("created_at") or ""
        date = f"{raw[:10]} {raw[11:16]}" if len(raw) >= 16 else raw[:10]
        mem_lines.append(f"• {date} {text}" if date else f"• {text}")
    if not mem_lines:
        return

    parts = mem_lines[:5]
    ctx.add_section("浮现的记忆", "\n".join(parts))


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="association_recall",
        description="背景关联记忆",
        execute=execute,
        enabled=True,
        required=False,
    )
