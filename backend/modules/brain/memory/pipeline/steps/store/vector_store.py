"""
VectorStore Step - 向量存储（required）
通过统一接口层 memory_store() 写入 Qdrant（aibrain_memories）

写入 ctx.intermediate:
  - mem0_result: memory_store() 返回的原始结果
  - mem0_ids: 提取的 ID 列表（字段名不变，下游无感）
  - mem_texts: 对应记忆文本列表
"""
import logging

from modules.brain.memory.store import memory_store

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 VectorStore 步骤：通过统一接口存储记忆

    Args:
        ctx: PipelineContext
            input_data: str (记忆文本)
            metadata: {"infer": bool, "memory_meta": dict, ...}
    """
    text = ctx.input_data
    meta = ctx.metadata or {}
    memory_meta = meta.get("memory_meta")

    # 组装 payload（完整元数据，未来 Phase 0 会注入 emotion/scene/temperature/hooks）
    payload = {"category": "user"}
    if memory_meta:
        payload.update(memory_meta)

    logger.info("[step:vector_store] calling memory_store...")
    result = memory_store(text, payload=payload)
    logger.info("[step:vector_store] memory_store DONE")

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
        description="向量存储（required）",
        execute=execute,
        enabled=True,
        required=True,
        pipeline="store",
        timeout=10.0,
    )
