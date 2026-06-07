"""
ChatManager — 聊天模块单例

职责：
- 用户交互：直接调 LLM 流式返回（不走线程）
- 空闲思绪：管理 ConsciousnessLoop（agentloop）生命周期
"""
from __future__ import annotations
import logging
import threading
from typing import Optional

from .agent_loop import ConsciousnessLoop
from .loop import send_message

logger = logging.getLogger(__name__)


class ChatManager:
    """聊天模块单例"""

    _instance: Optional['ChatManager'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop: Optional[ConsciousnessLoop] = None
        # LLM 配置缓存
        self._provider = "openai"
        self._model = "gpt-4o-mini"
        self._api_key = ""
        self._base_url = ""

    @classmethod
    def get_instance(cls) -> 'ChatManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 配置 ──────────────────────────────────────────────

    def load_config(self, config: dict):
        """加载 Chat 配置"""
        self._provider = config.get('chat_provider', 'openai')
        self._model = config.get('chat_model', 'gpt-4o-mini')
        self._api_key = config.get('chat_api_key', '')
        self._base_url = config.get('chat_base_url', '')
        # system_persona 已迁移到 PromptPipeline，此处不再使用

    # ── 用户交互（直接调 LLM，无线程） ─────────────────

    def send(self, prompt: str):
        """发送消息，返回 generator 逐 token 输出

        自动写工作记忆 + 注入 prompt。路由层：
            for event in mgr.send("你好"):
                yield f"data: {json.dumps(event)}\n\n"
        """
        return send_message(
            prompt,
            provider=self._provider,
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
        )

    # ── 空闲思绪（后台线程） ───────────────────────────

    def init_agentloop(self, stats_db, config: dict) -> ConsciousnessLoop:
        """初始化空闲思绪后台线程"""
        if self._loop is not None:
            return self._loop
        self._loop = ConsciousnessLoop(stats_db, config)
        if config.get('chat_api_key'):
            self._loop.start()
        return self._loop

    def stop_agentloop(self, timeout: float = 5.0):
        """停止空闲思绪线程"""
        if self._loop:
            self._loop.stop(timeout=timeout)
            self._loop = None

    def get_loop_state(self) -> dict:
        """获取空闲思绪状态"""
        if self._loop is None:
            return {
                'is_running': False, 'idle_enabled': False,
                'idle_count': 0, 'is_busy': False,
            }
        return self._loop.get_state()

    def reload_agentloop_config(self, config: dict):
        """热加载空闲思绪配置"""
        if self._loop:
            self._loop.reload_config(config)

    def set_mem0_add_fn(self, fn):
        """注入 mem0 add 函数（供空闲思绪写回用）"""
        if self._loop:
            self._loop.set_mem0_add_fn(fn)


def get_chat_manager() -> ChatManager:
    return ChatManager.get_instance()
