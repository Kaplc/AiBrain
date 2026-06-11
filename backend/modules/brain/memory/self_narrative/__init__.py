"""
自我叙事模块 (Layer S) — "我是谁"的核心叙事层

提供自传文档管理、对话后反思、叙事锚点标记、核心记忆保护。
外部通过 get_self_narrative() 获取单例。
"""
import logging

logger = logging.getLogger('self_narrative')

_INSTANCE = None


def init_self_narrative(graph) -> 'SelfNarrativeStore | None':
    """初始化 SelfNarrativeStore 单例，在 app 启动时调用

    Args:
        graph: GraphMemory 实例（复用其 SQLite 连接）

    Returns:
        SelfNarrativeStore 实例，失败返回 None
    """
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    try:
        from .narrative_store import SelfNarrativeStore
        _INSTANCE = SelfNarrativeStore(graph)
        logger.info("[self_narrative] SelfNarrativeStore initialized")
        return _INSTANCE
    except Exception as e:
        logger.warning(f"[self_narrative] init failed (non-fatal): {e}")
        return None


def get_self_narrative() -> 'SelfNarrativeStore | None':
    """获取 SelfNarrativeStore 单例，未初始化时返回 None"""
    return _INSTANCE
