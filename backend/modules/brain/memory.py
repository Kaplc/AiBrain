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

# 记忆数量缓存：启动时预热，store 时自增，避免每次搜索都调 get_all
_memory_count_cache = None


def warmup_memory_count():
    """预热记忆数量缓存（在 _preload 中调用）"""
    global _memory_count_cache
    try:
        client = get_mem0_client()
        result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=1)
        _memory_count_cache = len(result.get("results", []))
        logger.info(f"[memory] 记忆数量缓存已预热: {_memory_count_cache} 条")
    except Exception as e:
        logger.warning(f"[memory] 预热记忆数量失败: {e}")
        _memory_count_cache = 0


def get_client():
    """兼容接口：返回 mem0 客户端"""
    return get_mem0_client()


def _get_search_options():
    """根据数据量自适应返回最优搜索参数（使用缓存，避免每次 get_all）"""
    global _memory_count_cache
    if _memory_count_cache is None:
        # 缓存未预热时临时查询一次
        try:
            client = get_mem0_client()
            result = client.get_all(filters={"user_id": DEFAULT_USER_ID}, top_k=1)
            _memory_count_cache = len(result.get("results", []))
        except Exception:
            _memory_count_cache = 0
    total = _memory_count_cache

    if total < 100:
        return {"top_k": 50, "threshold": 0.55, "rerank": False}
    elif total <= 1000:
        return {"top_k": 50, "threshold": 0.55, "rerank": False}
    else:
        return {"top_k": 50, "threshold": 0.55, "rerank": True}


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

    # 有新增时自增缓存计数
    global _memory_count_cache
    if added and _memory_count_cache is not None:
        _memory_count_cache += len(added)

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
    """搜索记忆，直接请求高于阈值的结果，不足 15 条时补足。

    Returns:
        list[dict]: [{id, text, score}, ...]
    """
    client = get_mem0_client()
    opts = _get_search_options()

    threshold = opts.get("threshold", 0.55)
    rerank = opts.get("rerank", False)
    MIN_COUNT = 15

    # 第一次请求：只拿高于阈值的
    kwargs = {
        "query": query,
        "filters": {"user_id": DEFAULT_USER_ID},
        "top_k": 75,
        "threshold": threshold,
    }
    if rerank:
        kwargs["rerank"] = rerank

    result = client.search(**kwargs)
    memories = []
    for r in result.get("results", []):
        memories.append({
            "id": r.get("id"),
            "text": r["memory"],
            "score": round(r.get("score", 0), 4),
        })
    memories.sort(key=lambda x: x["score"], reverse=True)

    # 不足 MIN_COUNT 时，去掉阈值再请求补足
    if len(memories) < MIN_COUNT:
        kwargs_no_thresh = {
            "query": query,
            "filters": {"user_id": DEFAULT_USER_ID},
            "top_k": MIN_COUNT,
        }
        if rerank:
            kwargs_no_thresh["rerank"] = rerank
        result2 = client.search(**kwargs_no_thresh)
        seen_ids = {m["id"] for m in memories}
        for r in result2.get("results", []):
            if r.get("id") not in seen_ids:
                memories.append({
                    "id": r.get("id"),
                    "text": r["memory"],
                    "score": round(r.get("score", 0), 4),
                })
                seen_ids.add(r.get("id"))
        memories.sort(key=lambda x: x["score"], reverse=True)
        memories = memories[:MIN_COUNT]

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


def dedup_memories(threshold: float = 0.85) -> dict:
    """全量记忆去重分组（两步法第一步）"""
    from .dedup import dedup_memories as _dedup
    return _dedup(threshold)


def refine_memories(groups: list[dict]) -> dict:
    """LLM 精炼合并相似记忆组（两步法第二步）"""
    from .llm import refine_group

    refined = []
    for group in groups:
        result = refine_group(group["memories"])
        result["group_id"] = group.get("group_id", 0)
        refined.append(result)

    return {"refined": refined}


def apply_organize(items: list[dict]) -> dict:
    """用户确认后写入整理结果（删旧存新）"""
    applied = 0
    deleted = 0
    added = 0
    details = []

    for item in items:
        delete_ids = item.get("delete_ids", [])
        new_text = item.get("new_text", "").strip()

        if not new_text:
            continue

        # 先删旧
        for mem_id in delete_ids:
            try:
                delete_memory(mem_id)
                deleted += 1
            except Exception as e:
                logger.warning(f"[apply] 删除失败 {mem_id}: {e}")

        # 再存新
        try:
            res = store_memory(new_text)
            added += 1
            new_id = res.get("stored_texts", [""])[0] if res.get("stored_texts") else ""
            details.append({"deleted_ids": delete_ids, "new_id": new_id, "new_text": new_text})
        except Exception as e:
            logger.warning(f"[apply] 存储失败: {e}")
            details.append({"deleted_ids": delete_ids, "new_id": "", "new_text": new_text, "error": str(e)})

        applied += 1

    return {"applied": applied, "deleted": deleted, "added": added, "details": details}
