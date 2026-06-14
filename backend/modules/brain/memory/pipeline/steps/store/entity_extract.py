"""
EntityExtract Step - LLM 实体提取
从记忆文本中提取实体名列表和归属分类

读取 ctx.intermediate:
  - mem_texts: 记忆文本列表

写入 ctx.intermediate:
  - entities: 所有事件的实体名列表（合并去重）
  - entity_details: [{mem0_id, mem_text, entities, root_entity}, ...] 每条记忆的实体详情
"""
import logging

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 EntityExtract 步骤：LLM 提取实体

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:entity_extract] infer=false, skip LLM")
        return

    mem_texts = ctx.intermediate.get("mem_texts")
    mem0_ids = ctx.intermediate.get("mem0_ids")
    events = ctx.metadata.get("_events", [])

    if not events:
        logger.info("[step:entity_extract] no events to extract entities from")
        return

    from modules.brain.llm import extract_entities_llm

    all_entity_names = []
    entity_details = []

    for ev in events:
        if ev.get("event") != "ADD" or not ev.get("id"):
            continue
        mem_text = ev.get("memory", "")
        mem0_id = ev["id"]
        try:
            logger.info(f"[step:entity_extract] extracting entities | mem0_id={mem0_id[:8]}")
            result = extract_entities_llm(mem_text)
            auto_entity_names = result.get("entities", [])
            auto_nodes = result.get("nodes") or [
                {"name": n, "type": "concept"} for n in auto_entity_names
            ]
            root_entity = result.get("root", "用户")
            logger.info(f"[step:entity_extract] entities={auto_entity_names} | root={root_entity}")
        except Exception:
            auto_entity_names = []
            auto_nodes = []
            root_entity = "用户"
            logger.warning(f"[step:entity_extract] LLM failed for {mem0_id[:8]}")

        if not auto_entity_names:
            logger.info(f"[step:entity_extract] no entities, skip | mem0_id={mem0_id[:8]}")
            continue

        entity_details.append({
            "mem0_id": mem0_id,
            "mem_text": mem_text,
            "entities": auto_entity_names,
            "nodes": auto_nodes,
            "root_entity": root_entity,
        })
        all_entity_names.extend(auto_entity_names)

    # 写入 intermediate
    ctx.intermediate["entities"] = list(dict.fromkeys(all_entity_names))
    ctx.intermediate["entity_details"] = entity_details

    logger.info(f"[step:entity_extract] total entities={len(all_entity_names)} unique={len(ctx.intermediate['entities'])}")


def _make_step():
    """创建 EntityExtract StepDef"""
    from ...context import StepDef
    return StepDef(
        name="entity_extract",
        description="LLM 实体提取",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=30.0,
    )
