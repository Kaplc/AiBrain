"""内部状态层 section — 激活关注 + 注入内心状态到 prompt

这一节做两件事（plan S010-S014 合并为一节，避免 prompt 膨胀）：
  1. 状态更新（副作用）：从本次搜索结果收集实体 → 激活 concern、刷新 working_set、
     扫描生成 pending、挑选一条要表达的并记录冷却。
  2. prompt 注入：把 self / top concerns / open loops / 想顺带提的事 拼成
     【内心状态】一段，供 LLM 回复时体现「持续在想」。

注意：搜索（graph_recall）在本节之前已跑完，所以本节激活的 concern 要到【下一轮】
搜索才进入 concern_bias——这与人注意的「先注意、后回忆被启动」一致，是有意为之。

全包 try/except 静默降级，绝不阻断对话。
"""
from ..context import PromptContext


def _collect_entities(ctx: PromptContext) -> list[str]:
    """从语义搜索结果收集实体（canonical 名，已存在于 entity_nodes）。"""
    results = ctx.work_memory.get("package", {}).get("results", [])
    mem_ids = [r.get("id") for r in results if r.get("id")]
    if not mem_ids:
        return []
    try:
        from modules.brain.graph import get_graph
        graph = get_graph()
        if graph is None:
            return []
        entity_map = graph.get_entities_for_memories(mem_ids)
    except Exception:
        return []
    ents = []
    for mid in mem_ids:
        ents.extend(entity_map.get(mid, []))
    return list(dict.fromkeys(ents))


def _activate_and_collect(top_entities: list[str]) -> tuple[list, list, dict | None]:
    """激活 concern、刷 working_set、生成 pending；返回 (top_concerns, open_loops, pick)。"""
    try:
        from modules.brain.state import (
            get_concerns, get_working_set, get_open_loops, get_pending,
        )
    except Exception:
        return ([], [], None)

    concerns = get_concerns()
    for ent in top_entities[:8]:
        concerns.activate(ent)  # 用户消息触发，boost 0.15

    ws = get_working_set()
    for ent in top_entities[:5]:
        ws.upsert("node", ent, score=0.6, source="search_hit")

    get_pending().evaluate_and_generate()
    pick = get_pending().pick_to_send()
    if pick:
        # 注入提示后乐观标记已表达（记录 24h 冷却），不写 output（编入回复而非单独消息）
        get_pending().mark_expressed(pick["id"])

    return (concerns.all_effective(5), get_open_loops().summary_lines(3), pick)


def _build_hint(pick: dict) -> str:
    """把选中的 pending 意图转成给 LLM 的轻提示。"""
    try:
        from modules.brain.state import get_open_loops
    except Exception:
        get_open_loops = None
    if pick.get("source") == "open_loop" and get_open_loops:
        for loop in get_open_loops().get_open():
            if loop.get("id") == pick.get("source_node_id") and loop.get("content"):
                return f"有个一直没想明白的问题想顺带聊聊：{loop['content']}"
        return "有个一直没想明白的问题想顺带聊聊。"
    node = pick.get("source_node_id", "")
    return f"最近一直在意「{node}」，回复时可以自然地提一下。" if node else ""


def execute(ctx: PromptContext) -> None:
    try:
        top_ents = _collect_entities(ctx)
        top_concerns, loop_lines, pick = _activate_and_collect(top_ents)

        lines = []
        # top concerns：只列有效激活值 >=0.1 的（身份/自我由 self_narrative 节负责，不重复）
        concern_names = [nid for nid, eff in top_concerns if eff >= 0.1]
        if concern_names:
            lines.append("最近在关注：" + "、".join(concern_names[:5]) + "。")

        if loop_lines:
            lines.append("还没想明白：\n" + "\n".join(loop_lines))

        if pick:
            hint = _build_hint(pick)
            if hint:
                lines.append(hint)

        if lines:
            ctx.add_section("内心状态", "\n".join(lines))
    except Exception:
        pass


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="internal_state",
        description="内部状态激活与注入",
        execute=execute,
        enabled=True,
        required=False,
    )
