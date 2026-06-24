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
        self._tools_enabled = False
        # 当前处理状态（供前端流式显示）
        self._current_status = ""
        self._status_lock = threading.Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._stats_db = None
        # 记忆搜索步骤缓冲区（LLM 检查、语义搜索、图扩散等，供 SSE 推送到前端）
        self._memory_steps: list[dict] = []
        self._memory_steps_lock = threading.Lock()
        # Reactive BrainSession 最近一次内部思考（供 brain_context section 注入）
        self._brain_context: dict = {}
        self._current_trace_id: str = ""
        self._current_parent_event_id: str = ""

    @classmethod
    def get_instance(cls) -> 'ChatManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 状态跟踪 ──────────────────────────────────────────

    def set_status(self, status: str):
        """设置当前处理状态（线程安全）"""
        with self._status_lock:
            self._current_status = status

    def get_status(self) -> str:
        """获取当前处理状态"""
        with self._status_lock:
            return self._current_status

    def set_token_usage(self, prompt: int, completion: int):
        """记录 token 用量"""
        self._prompt_tokens = prompt
        self._completion_tokens = completion

    def push_memory_step(self, step: str, status: str):
        """追加一条搜索步骤事件（线程安全），供 SSE 流推送到前端

        Args:
            step: 步骤名称，如 "vector_search" / "graph_recall"
            status: "running" / "done"
        """
        with self._memory_steps_lock:
            self._memory_steps.append({"step": step, "status": status})

    def pop_memory_steps(self) -> list[dict]:
        """取出并清空所有未推送的步骤事件"""
        with self._memory_steps_lock:
            steps = list(self._memory_steps)
            self._memory_steps.clear()
            return steps

    def set_brain_context(self, ctx: dict) -> None:
        self._brain_context = ctx or {}

    def get_brain_context(self) -> dict:
        return getattr(self, "_brain_context", {}) or {}

    def set_event_trace(self, trace_id: str, event_id: str) -> None:
        self._current_trace_id = trace_id
        self._current_parent_event_id = event_id

    def get_event_trace(self) -> tuple[str, str]:
        return self._current_trace_id, self._current_parent_event_id

    # ── 配置 ──────────────────────────────────────────────

    def load_config(self, config: dict):
        """加载 LLM 配置（读 llm.json，设置→LLM 页面配的）"""
        self._provider = config.get('provider', 'openai')
        self._model = config.get('model', 'gpt-4o-mini')
        self._api_key = config.get('api_key', '')
        self._base_url = config.get('base_url', '')
        # system_persona / tools_enabled 使用默认值（ChatTab 已移除）
        self._tools_enabled = config.get('tools_enabled', True)
        self._system_persona = config.get('system_persona', '')

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
            tools_enabled=self._tools_enabled,
            system_persona=self._system_persona,
        )

    # ── 空闲思绪（后台线程） ───────────────────────────

    def init_agentloop(self, stats_db, config: dict) -> ConsciousnessLoop:
        """初始化空闲思绪后台线程"""
        self._stats_db = stats_db
        if self._loop is not None:
            return self._loop
        self._loop = ConsciousnessLoop(stats_db, config)
        if config.get('api_key') or config.get('chat_api_key'):
            self._loop.start()
        return self._loop

    def stop_agentloop(self, timeout: float = 5.0):
        """停止空闲思绪线程"""
        if self._loop:
            self._loop.stop(timeout=timeout)
            self._loop = None

    def get_loop_state(self) -> dict:
        """获取空闲思绪状态 + 当前处理状态 + token 用量"""
        state = self._loop.get_state() if self._loop else {
            'is_running': False, 'idle_enabled': False,
            'idle_count': 0, 'is_busy': False,
        }
        state['current_status'] = self.get_status()
        # 内存中最后一次 LLM 返回的 token 数；页面刷新后从数据库读取最近一次记录
        prompt_tokens = self._prompt_tokens
        completion_tokens = self._completion_tokens
        if prompt_tokens <= 0 and self._stats_db:
            try:
                last = self._stats_db.get_last_token_usage()
                if last:
                    self._prompt_tokens = last.get("prompt_tokens", 0)
                    self._completion_tokens = last.get("completion_tokens", 0)
                    prompt_tokens = self._prompt_tokens
                    completion_tokens = self._completion_tokens
                    logger.info(f"[token] loaded from db → memory: prompt={prompt_tokens} completion={completion_tokens}")
            except Exception as e:
                logger.warning(f"[token] db fallback failed: {e}")
        state['prompt_tokens'] = prompt_tokens
        state['completion_tokens'] = completion_tokens
        try:
            from .compression.compress_config import MAX_CONTEXT_TOKENS
            state['max_context_tokens'] = MAX_CONTEXT_TOKENS
        except Exception:
            state['max_context_tokens'] = 400000
        return state

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
