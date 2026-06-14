"""
GraphLink Step - 图链接
将提取的实体链接到实体网络

读取 ctx.intermediate:
  - entity_details: [{mem0_id, mem_text, entities, root_entity}, ...]

写入 ctx.intermediate:
  - graph_result: 图链接结果（简单标记）
"""
import logging

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 GraphLink 步骤：将实体链接到图网络

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:graph_link] infer=false, skip")
        return

    entity_details = ctx.intermediate.get("entity_details")
    if not entity_details:
        logger.info("[step:graph_link] no entity_details, skip")
        return

    from modules.brain.graph import get_graph
    graph = get_graph()
    if not graph:
        logger.warning("[step:graph_link] graph not available, skip")
        return

    all_entity_names = []
    for detail in entity_details:
        mem0_id = detail["mem0_id"]
        mem_text = detail["mem_text"]
        entities = detail["entities"]
        root_entity = detail["root_entity"]

        try:
            logger.info(
                f"[step:graph_link] linking | mem0_id={mem0_id[:8]} | "
                f"entities={entities} | root={root_entity}"
            )
            graph.link_memory(
                mem0_id, mem_text,
                link_entities=entities,
                root_entity=root_entity
            )
            graph.increment_entity_counts(entities)
            graph.increment_co_activation(entities)
            all_entity_names.extend(entities)
            logger.info(f"[step:graph_link] done | mem0_id={mem0_id[:8]} | count={len(entities)}")
        except Exception as e:
            logger.warning(f"[step:graph_link] failed for {mem0_id[:8]}: {e}")

    ctx.intermediate["graph_result"] = True

    # 合并更新 ctx.intermediate["entities"]（确保完整去重列表）
    existing = ctx.intermediate.get("entities", [])
    merged = list(dict.fromkeys(existing + all_entity_names))
    ctx.intermediate["entities"] = merged

    logger.info(f"[step:graph_link] DONE | total linked entities={len(all_entity_names)}")


def _make_step():
    """创建 GraphLink StepDef"""
    from ...context import StepDef
    return StepDef(
        name="graph_link",
        description="图链接",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=15.0,
    )
