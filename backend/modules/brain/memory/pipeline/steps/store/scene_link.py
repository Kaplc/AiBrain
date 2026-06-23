"""
SceneLink Step - 情景图索引建边（store 管道）
读取 encoder 产出的 memory_meta.nodes + 向量存储后的 scene id，
建立 scene→anchor 边与 scene→scene 候选边（限边），写入情景图索引。

Pipeline 位置：store 管道末尾（vector_store 之后，需要 scene id）。
只对 infer=True（情景模式）生效；nodes 已由 encoder 规范化，本层不重复 embed。
图索引失败不阻塞存储（异常流程 #3：Qdrant 写入仍算成功，图层可异步补建）。
"""
import logging

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 SceneLink 步骤：建立情景图索引

    Args:
        ctx: PipelineContext
            intermediate.mem0_ids: vector_store 写入的 scene id 列表
            metadata.memory_meta: encoder 产出的 {nodes, affect, importance, ...}
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:scene_link] infer=false, skip")
        return

    mem_meta = meta.get("memory_meta") or {}
    nodes = mem_meta.get("nodes") or []
    if not nodes:
        logger.info("[step:scene_link] no nodes in memory_meta, skip")
        return

    mem0_ids = ctx.intermediate.get("mem0_ids") or []
    if not mem0_ids:
        logger.info("[step:scene_link] no mem0_ids, skip")
        return

    from modules.brain.memory.scene_graph import get_scene_graph
    sg = get_scene_graph()
    if not sg:
        logger.warning("[step:scene_link] scene graph unavailable, skip")
        return

    affect = mem_meta.get("affect")
    importance = mem_meta.get("importance", 0.3)
    for sid in mem0_ids:
        try:
            sg.link_scene(sid, nodes, affect=affect, importance=importance)
            logger.info(f"[step:scene_link] linked scene={sid[:8]} | nodes={len(nodes)}")
        except Exception as e:
            # 非致命：Qdrant 主存储已成功，图层失败可后续 reindex 补建
            logger.warning(f"[step:scene_link] failed for {sid[:8]} (non-fatal): {e}")


def _make_step():
    """创建 SceneLink StepDef"""
    from ...context import StepDef
    return StepDef(
        name="scene_link",
        description="情景图索引建边（scene-anchor + scene-scene）",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=10.0,
    )
