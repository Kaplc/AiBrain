"""
EpisodicMerge Step - 情景记忆写入前去重合并（去重合并专用）

在 encoder 之前运行。用语义搜索查找相似记忆，发现高度相似的已有记忆时，
将新记忆与旧记忆合并成一条精炼记忆，删除旧记忆，然后让 encoder 正常编码合并后的文本。

Pipeline 位置：store 管道第一步骤（在 encoder 之前）
只对 infer=True（情景模式）生效。
"""
import json
import logging

logger = logging.getLogger('memory.pipeline')

_MERGE_THRESHOLD = 0.85
_MERGE_TOP_K = 5

_MERGE_PROMPT = """你是一个记忆合并助手。给定多条描述同一件事或相关话题的记忆文本，将它们合并成一条精炼、完整的记忆。

要求：
- 保留所有重要信息，去重
- 按时间顺序或逻辑连贯性组织
- 保留最具体的细节，删除模糊重复的部分
- 如果有冲突信息，保留更具体或更新那条
- 合并后保留完整叙事

输出严格的 JSON，不要解释文字：
{"merged_text": "合并后的完整记忆文本", "display_text": "一句话标题（8-20字）"}"""


def execute(ctx) -> None:
    """执行 EpisodicMerge 步骤：语义搜索相似记忆 → 合并 → 删除旧记忆

    Args:
        ctx: PipelineContext
            input_data: str (原始记忆文本)
            metadata: {"infer": bool, ...}
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:episodic_merge] infer=false, skip")
        return

    text = ctx.input_data
    if not text or not str(text).strip():
        logger.info("[step:episodic_merge] empty text, skip")
        return

    # 1. 语义搜索相似记忆
    from modules.brain.memory.store import memory_search
    similar = memory_search(str(text), top_k=_MERGE_TOP_K, threshold=_MERGE_THRESHOLD)
    # 过滤掉自己（刚保存的相同内容不可能存在，但以防万一）
    similar = [m for m in similar if m.get("text", "") != str(text)]
    if not similar:
        logger.info("[step:episodic_merge] no similar memories found, skip")
        return

    logger.info(
        f"[step:episodic_merge] found {len(similar)} similar memories | "
        f"top_score={similar[0].get('score', 0):.4f}"
    )
    for s in similar:
        logger.info(f"  └─ [{s.get('score', 0):.4f}] {s.get('id', '')[:8]} | {str(s.get('text', ''))[:60]}")

    # 2. 收集新旧文本，调用 LLM 合并
    old_ids = [m["id"] for m in similar if m.get("id")]
    old_texts = [str(m.get("text", "")) for m in similar if m.get("text")]

    merge_input = "--- 新记忆 ---\n" + str(text)
    for i, old_t in enumerate(old_texts):
        merge_input += f"\n\n--- 相似记忆 {i + 1} ---\n{old_t}"

    from modules.brain.llm import call_llm
    from modules.brain.memory.self_narrative.utils import parse_json

    try:
        logger.info(f"[step:episodic_merge] merging {len(old_texts) + 1} texts...")
        raw = call_llm(_MERGE_PROMPT, merge_input, timeout=30)
        result = parse_json(raw)
        if result is None or not isinstance(result, dict):
            logger.warning(f"[step:episodic_merge] LLM returned invalid JSON: {str(raw)[:120]!r}")
            return

        merged_text = (result.get("merged_text") or "").strip()
        display_text = (result.get("display_text") or "").strip()
        if not merged_text:
            logger.warning("[step:episodic_merge] merged_text is empty, abort merge")
            return

        logger.info(f"[step:episodic_merge] merged OK | display={display_text!r} | old_ids={[i[:8] for i in old_ids]}")
    except Exception as e:
        logger.warning(f"[step:episodic_merge] LLM merge failed: {e}")
        return

    # 3. 更新 ctx：用合并后的文本替换原文，encoder 后续会编码它
    ctx.input_data = merged_text
    ctx.metadata["_merged_from_ids"] = old_ids

    # 4. 删除旧记忆（Qdrant + graph）
    _delete_old_memories(old_ids)

    logger.info(
        f"[step:episodic_merge] DONE | merged {len(old_texts) + 1} texts | "
        f"deleted {len(old_ids)} old memories | display={display_text!r}"
    )


def _delete_old_memories(memory_ids: list[str]) -> None:
    """从 Qdrant 和 graph 中删除旧记忆，不抛出异常"""
    if not memory_ids:
        return

    # Qdrant 删除
    try:
        from qdrant_client.http import models as q
        from modules.brain.memory.qdrant_store import get_qdrant_client, NEW_COLLECTION, LEGACY_COLLECTION

        client = get_qdrant_client()
        client.delete(
            collection_name=NEW_COLLECTION,
            points_selector=q.PointIdsList(points=memory_ids),
            wait=True,
        )
        # 也尝试从旧集合删
        try:
            client.delete(
                collection_name=LEGACY_COLLECTION,
                points_selector=q.PointIdsList(points=memory_ids),
                wait=True,
            )
        except Exception:
            pass
        logger.info(f"[episodic_merge] deleted {len(memory_ids)} points from Qdrant")
    except Exception as e:
        logger.warning(f"[episodic_merge] Qdrant delete failed (non-fatal): {e}")

    # Graph 删除
    try:
        from modules.brain.graph import get_graph
        graph = get_graph()
        if graph:
            for mid in memory_ids:
                graph.delete_memory(mid)
        logger.info(f"[episodic_merge] deleted {len(memory_ids)} from graph")
    except Exception as e:
        logger.warning(f"[episodic_merge] graph delete failed (non-fatal): {e}")

    # Scene graph 删除（情景图索引同步清理，避免孤儿边）
    try:
        from modules.brain.memory.scene_graph import get_scene_graph
        sg = get_scene_graph()
        if sg:
            for mid in memory_ids:
                sg.delete_scene(mid)
        logger.info(f"[episodic_merge] deleted {len(memory_ids)} from scene graph")
    except Exception as e:
        logger.warning(f"[episodic_merge] scene graph delete failed (non-fatal): {e}")


def _make_step():
    """创建 EpisodicMerge StepDef"""
    from ...context import StepDef
    return StepDef(
        name="episodic_merge",
        description="情景记忆写入前去重合并（语义搜索+LLM合并+删除旧记忆）",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=35.0,
    )
