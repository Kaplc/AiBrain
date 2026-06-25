"""
SceneRecall Step - 情景图扩散召回（search 管道）
以语义命中 payload.nodes 为种子做 scene→anchor→scene 扩散，输出带 trace 的候选记忆。

新图主召回路径（FR-003/007/010）：旧实体共现召回 graph_recall 已移除，
情景图扩散成为唯一的图召回来源；新图不可用时退回纯语义命中（vector_search）。

读取 ctx.intermediate:
  - semantic_results: 语义命中（含 payload.nodes）

写入 ctx.intermediate:
  - scene_results: 扩散召回的候选记忆 [{id,text,score,source,trace,...}]
"""
import logging

logger = logging.getLogger('memory.pipeline')


def _push_step(step: str, status: str):
    """向 ChatManager 推送步骤事件，供 SSE 流推送到前端"""
    try:
        from modules.chat import ChatManager
        ChatManager.get_instance().push_memory_step(step, status)
    except Exception:
        pass


def execute(ctx) -> None:
    """执行 SceneRecall 步骤：情景图扩散召回

    Args:
        ctx: PipelineContext
            input_data: str (query)
            intermediate.semantic_results: 语义命中列表
    """
    _push_step("scene_recall", "running")

    query = ctx.input_data
    semantic_results = ctx.intermediate.get("semantic_results") or []
    if not semantic_results:
        logger.info("[step:scene_recall] no semantic_results, skip")
        _push_step("scene_recall", "done")
        ctx.intermediate["scene_results"] = []
        return

    from ....scene_diffusion import get_scene_diffusion
    diff = get_scene_diffusion()
    if not diff or not diff.available():
        # 新图不可用 → 本步跳过，检索退回纯语义命中（异常流程 #4）
        logger.info("[step:scene_recall] scene diffusion unavailable, skip")
        _push_step("scene_recall", "done")
        ctx.intermediate["scene_results"] = []
        return

    candidates = diff.search(query, semantic_results, top_k=20, with_trace=True)
    # 与语义命中去重（同一 id 不重复入列）
    seen = {m.get("id") for m in semantic_results if m.get("id")}
    candidates = [c for c in candidates if c.get("id") not in seen]

    ctx.intermediate["scene_results"] = candidates
    logger.info(f"[step:scene_recall] DONE | scene diffusion recall={len(candidates)}")
    for c in candidates:
        tr = c.get("trace", {})
        logger.info(
            f"  └─ [{c.get('score', 0):.4f}] {c.get('id', '')[:8]} | "
            f"hop={tr.get('hop')} rel={tr.get('relation_type')} | {c.get('text', '')[:60]}"
        )
    _push_step("scene_recall", "done")


def _make_step():
    """创建 SceneRecall StepDef"""
    from ...context import StepDef
    return StepDef(
        name="scene_recall",
        description="情景图扩散召回（scene-anchor-scene）",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="search",
        timeout=20.0,
    )
