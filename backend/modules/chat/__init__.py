"""Chat 聊天模块

外部访问：
    from modules.chat import ChatManager
    mgr = ChatManager.get_instance()
    mgr.load_config(config)

    # 用户交互（直接，无线程）
    for event in mgr.send("你好"):
        ...

    # 空闲思绪（后台线程）
    mgr.init_agentloop(stats_db, config)
"""
from .chat_mod import ChatManager, get_chat_manager
from .agent_loop import ConsciousnessLoop

__all__ = [
    "ChatManager",
    "get_chat_manager",
    "ConsciousnessLoop",
]
