"""
记忆核心逻辑 - 基于 mem0 实现
mem0 全权管理：存储、去重、自动更新、自适应搜索。
MCP 只暴露 store + search，其余给前端 UI 用。
"""
import logging

from modules.brain.mem0_adapter import get_mem0_client

logger = logging.getLogger('memory')

# 默认 user_id，mem0 需要至少一个 entity id
DEFAULT_USER_ID = "default"


def get_client():
    """兼容接口：返回 mem0 客户端"""
    return get_mem0_client()


def _get_search_options():
    """根据数据量自适应返回最优搜索参数。

    数据量 < 100:     top_k=15,  threshold=None,  rerank=False   （全召回）
    数据量 100~1000:  top_k=15,  threshold=0.5,    rerank=False   （轻过滤）
    数据量 > 1000:    top_k=15,  threshold=0.65,   rerank=True    （精确+重排）

    top_k 固定不变——控制"想看几条"，不随数据量变化。
    threshold 控制质量底线，rerank 在数据量大时提升排序精度。
    """
    try:
        client = get_mem0_client()
        count_result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=1)
        total = len(count_result.get("results", []))
    except Exception:
        total = 0

    if total < 100:
        return {"top_k": 15, "threshold": None, "rerank": False}
    elif total <= 1000:
        return {"top_k": 15, "threshold": 0.5, "rerank": False}
    else:
        return {"top_k": 15, "threshold": 0.65, "rerank": True}


def store_memory(text: str) -> dict:
    """存储记忆，LLM 自动从文本中拆分多条事实。

    Returns:
        dict: 包含 result 消息和实际存入的原始文本列表
            {"result": "已记住: 新增 N 条记忆", "stored_texts": [...]}
    """
    client = get_mem0_client()
    try:
        result = client.add(
            text,
            user_id=DEFAULT_USER_ID,
            infer=True,
        )
    except Exception as e:
        logger.warning(f"store_memory failed (infer=True): {e}, fallback infer=False")
        result = client.add(
            text,
            user_id=DEFAULT_USER_ID,
            infer=False,
        )

    # 完整日志：记录 mem0 返回的原始结果
    logger.info(f"[store_memory] mem0 raw result: {result}")
    logger.info(f"[store_memory] input text: {text}")

    events = result.get("results", [])

    added = [e["memory"] for e in events if e.get("event") == "ADD"]
    updated = [e["memory"] for e in events if e.get("event") == "UPDATE"]

    parts = []
    if added:
        parts.append(f"新增 {len(added)} 条记忆")
    if updated:
        parts.append(f"更新 {len(updated)} 条记忆")

    # 收集所有被记住的原始文本（用于 MCP 返回显示）
    stored_texts = added + updated
    msg = f"已记住: {', '.join(parts)}" if parts else "已处理"

    return {"result": msg, "stored_texts": stored_texts}


def search_memory(query: str) -> list[dict]:
    """搜索记忆，后端自动根据数据量选择最优策略。

    Returns:
        list[dict]: [{id, text, score}, ...]
    """
    client = get_mem0_client()
    opts = _get_search_options()

    kwargs = {"query": query, "filters": {"user_id": DEFAULT_USER_ID}}
    if opts.get("top_k"):
        kwargs["top_k"] = opts["top_k"]
    if opts.get("threshold") is not None:
        kwargs["threshold"] = opts["threshold"]
    if opts.get("rerank"):
        kwargs["rerank"] = opts["rerank"]

    result = client.search(**kwargs)

    memories = []
    for r in result.get("results", []):
        memories.append({
            "id": r["id"],
            "text": r["memory"],
            "score": round(r.get("score", 0), 4),
        })
    return memories


def list_memories(offset: int = 0, limit: int = 200) -> list[dict]:
    """列出所有记忆（前端 UI 用），按最新时间倒序排列"""
    client = get_mem0_client()
    result = client.get_all(
        filters={"user_id": DEFAULT_USER_ID},
        top_k=10000,
    )
    all_memories = result.get("results", [])
    # 按创建时间倒序（最新的在前面）
    all_memories.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    paged = all_memories[offset:offset + limit]
    return [
        {
            "id": m["id"],
            "text": m["memory"],
            "timestamp": m.get("created_at"),
        }
        for m in paged
    ]


def delete_memory(memory_id: str) -> str:
    """删除记忆（前端 UI 用）"""
    client = get_mem0_client()
    client.delete(memory_id)
    return f"已删除记忆: {memory_id}"


def update_memory(memory_id: str, new_text: str) -> str:
    """更新记忆（前端 UI 用，用户手动编辑时调用）"""
    client = get_mem0_client()
    client.update(memory_id, new_text)
    return f"已更新记忆: {new_text}"


def organize_memories(query: str) -> dict:
    """搜索相关记忆并整理（前端 UI 高级功能用）"""
    from .organizer import organize_memories as _organize

    related = search_memory(query)
    result = _organize(query, related)

    for mem_id in result["deleted_ids"]:
        delete_memory(mem_id)

    new_ids = []
    for mem in result.get("individual_memories", []):
        res = store_memory(mem["text"])
        new_ids.extend(res.get("stored_texts", []))

    result["new_memory_ids"] = new_ids
    result["new_memory_id"] = new_ids[0] if new_ids else None

    return result
