"""
Agents — LLM Agent 注册表

外部访问：
    from modules.LLM import get_agent_manager
    mgr = get_agent_manager()
    result = mgr.get("memory_search").run({"current": "你好"})
"""
from .agent_manager import AgentManager, get_agent_manager
from .base_agent import BaseAgent

__all__ = [
    "AgentManager",
    "get_agent_manager",
    "BaseAgent",
]


def register_all_agents():
    """注册所有 Agent（在 app.py 启动时调用）"""
    mgr = AgentManager.get_instance()
    from .memory_search_agent import MemorySearchAgent
    mgr.register(MemorySearchAgent())
    from .memory_relation_agent import MemoryRelationAgent
    mgr.register(MemoryRelationAgent())
    from .info_sufficient_agent import InfoSufficientAgent
    mgr.register(InfoSufficientAgent())
    import logging
    logging.getLogger(__name__).info(
        "[AgentManager] register_all_agents done, total=%d", len(mgr._registry)
    )
