"""
VectorStore Step - mem0 向量存储（required）
封装 mem0.add() 调用，处理 infer 降级重试

写入 ctx.intermediate:
  - mem0_result: mem0.add() 返回的原始结果
  - mem0_ids: 提取的 ID 列表
  - mem_texts: 对应记忆文本列表
"""
import logging

from modules.brain.mem0_adapter import get_mem0_client

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 VectorStore 步骤：调用 mem0.add() 存储记忆

    Args:
        ctx: PipelineContext
            input_data: str (记忆文本)
            metadata: {"infer": bool, "metadata": dict, ...}
    """
    text = ctx.input_data
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    memory_meta = meta.get("memory_meta")

    client = get_mem0_client()

    add_kwargs = {
        "user_id": "default",
        "infer": use_infer,
    }

    # 合并 metadata
    metadata = {"category": "user"}
    if memory_meta:
        metadata.update(memory_meta)
    add_kwargs["metadata"] = metadata

    try:
        logger.info("[step:vector_store] calling mem0.add...")
        result = client.add(text, **add_kwargs)
        logger.info("[step:vector_store] mem0.add DONE")
    except Exception as e:
        if use_infer:
            logger.warning(f"[step:vector_store] failed (infer=True): {e}, fallback infer=False")
            add_kwargs["infer"] = False
            result = client.add(text, **add_kwargs)
        else:
            raise

    logger.info(f"[step:vector_store] mem0 raw result: {result}")

    events = result.get("results", [])
    added = [e["memory"] for e in events if e.get("event") == "ADD"]
    updated = [e["memory"] for e in events if e.get("event") == "UPDATE"]
    deleted = [e["memory"] for e in events if e.get("event") == "DELETE"]

    mem0_ids = [e["id"] for e in events if e.get("event") == "ADD" and e.get("id")]
    mem_texts = [e.get("memory", "") for e in events if e.get("event") == "ADD" and e.get("id")]

    # 写入 intermediate 供下游步骤使用
    ctx.intermediate["mem0_result"] = result
    ctx.intermediate["mem0_ids"] = mem0_ids
    ctx.intermediate["mem_texts"] = mem_texts

    # 将解析结果写入 metadata 供兼容层使用
    ctx.metadata["_added"] = added
    ctx.metadata["_updated"] = updated
    ctx.metadata["_deleted"] = deleted
    ctx.metadata["_events"] = events

    # 更新记忆数量缓存
    from modules.brain.memory.core import _memory_count_cache
    import modules.brain.memory.core as core_mod
    if core_mod._memory_count_cache is not None:
        core_mod._memory_count_cache += len(added) - len(deleted)
        core_mod._memory_count_cache = max(0, core_mod._memory_count_cache)

    logger.info(f"[step:vector_store] added={len(added)} updated={len(updated)} deleted={len(deleted)}")


def _make_step():
    """创建 VectorStore StepDef"""
    from ...context import StepDef
    return StepDef(
        name="vector_store",
        description="mem0 向量存储（required）",
        execute=execute,
        enabled=True,
        required=True,
        pipeline="store",
        timeout=10.0,
    )
