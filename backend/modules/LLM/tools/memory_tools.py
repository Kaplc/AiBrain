"""
memory_tools — 记忆搜索与存储工具

封装 modules.brain.memory.core 的 search_memory / store_memory，
供 LLM function calling 调用。
"""
import logging

from .registry import ToolDef

logger = logging.getLogger(__name__)


def _memory_search_fn(query: str) -> str:
    """搜索长期记忆库，返回 top 5 结果的完整详情（含情景描述、情感、正文）"""
    from main_brain.memory.core import search_memory
    results = search_memory(query)
    if not results:
        return "没有找到相关记忆"
    lines = []
    for i, r in enumerate(results[:5], 1):
        text = r.get("text", "")
        score = r.get("score", 0)
        payload = r.get("payload") or {}

        # 标题 + 相似度
        entry = f"{i}. {text} (相似度: {score:.2f})"

        # 情景详情（核心内容）
        episodic = payload.get("episodic")
        if episodic and isinstance(episodic, dict):
            what = episodic.get("what", "")
            why = episodic.get("why", "")
            result = episodic.get("result", "")
            lesson = episodic.get("lesson", [])
            details = []
            if what:
                details.append(f"  情景: {what[:200]}")
            if why:
                details.append(f"  起因: {why[:200]}")
            if result:
                details.append(f"  结果: {result[:200]}")
            if lesson:
                details.append(f"  教训: {'; '.join(str(l)[:100] for l in lesson[:3])}")
            if details:
                entry += "\n" + "\n".join(details)

        # 情感分布
        affect = payload.get("affect")
        if affect and isinstance(affect, dict):
            affect_str = ", ".join(
                f"{k}:{v}" for k, v in affect.items()
                if isinstance(v, (int, float)) and v > 0
            )
            if affect_str:
                entry += f"\n  情感: {affect_str[:120]}"

        # 完整正文（embedding 源文本，包含最完整的信息）
        embed_text = payload.get("embedding_text", "")
        if embed_text and len(embed_text) > len(text):
            entry += f"\n  详情: {embed_text[:300]}"
            if len(embed_text) > 300:
                entry += "…"

        # 时间
        created_at = payload.get("created_at", "")
        if created_at:
            entry += f"\n  时间: {created_at[:19]}"

        lines.append(entry)
    return "\n\n".join(lines)


def _memory_store_fn(text: str) -> str:
    """保存信息到长期记忆库"""
    from main_brain.memory.core import store_memory
    result = store_memory(text, memory_meta={"source": "chat_tool"})
    return result.get("result", "已处理")


MEMORY_SEARCH_TOOL = ToolDef(
    name="memory_search",
    description="搜索长期记忆库。当用户问及过去的事件、偏好、事实信息时使用此工具查找相关记忆。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": '用自然语言描述你想搜索的内容（例如"小明的生日是什么时候"），不要只输关键词',
            }
        },
        "required": ["query"],
    },
    fn=_memory_search_fn,
)

MEMORY_STORE_TOOL = ToolDef(
    name="memory_store",
    description="保存信息到长期记忆库。当用户明确要求记住某事，或对话中出现了值得长期保存的重要信息时使用。",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要记住的信息文本",
            }
        },
        "required": ["text"],
    },
    fn=_memory_store_fn,
)


def register_memory_tools():
    """注册所有记忆工具到 ToolRegistry（在 _preload 中调用）"""
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(MEMORY_SEARCH_TOOL)
    reg.register(MEMORY_STORE_TOOL)
