"""
AgentManager - Agent 全局注册表单例

所有 Agent 统一在此注册，外部通过 AgentManager.get_instance().get(name) 获取。

用法：
    from .manager import AgentManager
    mgr = AgentManager.get_instance()
    mgr.register(MyAgent())
    agent = mgr.get("my_agent")
    result = agent.run(input_data)
"""
import logging
import threading
from typing import Optional

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentManager:
    """Agent 注册表单例"""

    _instance: Optional['AgentManager'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._registry: dict[str, BaseAgent] = {}

    @classmethod
    def get_instance(cls) -> 'AgentManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, agent: BaseAgent) -> None:
        self._registry[agent.name] = agent
        logger.info(f"[AgentManager] registered: {agent.name} - {agent.description}")

    def get(self, name: str) -> BaseAgent:
        if name not in self._registry:
            raise KeyError(f"Agent '{name}' 未注册。已注册: {list(self._registry.keys())}")
        return self._registry[name]

    def has(self, name: str) -> bool:
        return name in self._registry

    def list_agents(self) -> list[dict]:
        return [
            {"name": agent.name, "description": agent.description}
            for agent in self._registry.values()
        ]


def get_agent_manager() -> AgentManager:
    return AgentManager.get_instance()
