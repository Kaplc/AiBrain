"""
ConsciousnessLoop — 意识流守护线程（单例）

职责：
- 后台循环：用户 tick（SSE 流式）+ 空闲 tick（自由联想）
- 每 tick 自动从 mem0 检索相关记忆 → 注入 system prompt
- 空闲思绪写到独立 user_id='consciousness_agent'，物理隔离
- 连续失败冷却（10 次 → 5 分钟）
"""
from __future__ import annotations
import logging
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from modules.LLM import LLMConfig, call_llm_stream
from .prompts import (
    build_system_prompt,
    build_idle_prompt,
    format_memory_block,
    IDLE_CUES,
)

logger = logging.getLogger(__name__)


# ── 内部状态 ─────────────────────────────────────────────────
@dataclass
class _LoopState:
    is_running: bool = False
    # LLM 配置（原子替换）
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    # 意识流配置
    system_persona: str = ""
    idle_enabled: bool = False
    idle_interval_seconds: int = 45
    max_context_messages: int = 20
    # 运行时计数
    idle_count: int = 0
    last_thought_at: Optional[float] = None
    last_thought_preview: Optional[str] = None
    consecutive_failures: int = 0
    next_idle_at: float = field(default_factory=lambda: time.time() + 45)

    @property
    def llm_kwargs(self) -> dict:
        return dict(
            provider=self.llm_provider,
            model=self.llm_model,
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
        )


class ConsciousnessLoop:
    """意识流守护线程"""

    def __init__(self, stats_db, config: dict):
        self._stats_db = stats_db
        self._state = _LoopState()
        self._lock = threading.Lock()          # 串行化 tick
        self._config_lock = threading.Lock()   # 原子替换配置
        self._stop = threading.Event()
        self._user_event = threading.Event()   # 用户消息信号
        self._pending_user_prompt: str = ""
        self._pending_user_sink: Optional[queue.Queue] = None
        # mem0 检索函数（延迟注入）
        self._mem0_search_fn = None
        self._mem0_add_fn = None
        # mem0 写队列（异步写，不阻塞 tick）
        self._mem0_add_queue: queue.Queue = queue.Queue(maxsize=128)
        self._mem0_writer_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 初始化配置
        self._apply_config(config)

    # ── mem0 注入 ─────────────────────────────────────────
    def set_mem0_functions(self, search_fn, add_fn):
        """延迟注入 mem0 search/add 函数（由 app.py 在 _preload 后调用）"""
        self._mem0_search_fn = search_fn
        self._mem0_add_fn = add_fn

    # ── 生命周期 ──────────────────────────────────────────
    def start(self):
        """启动守护线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._mem0_writer_stop.clear()
        self._state.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="consciousness-loop")
        self._thread.start()
        # 启动 mem0 异步写线程
        threading.Thread(target=self._mem0_writer_loop, daemon=True, name="mem0-writer").start()
        logger.info("[consciousness] loop started")

    def stop(self, timeout: float = 5.0):
        """停止守护线程"""
        self._stop.set()
        self._user_event.set()  # 唤醒 wait
        self._mem0_writer_stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("[consciousness] loop did not stop gracefully")
        self._state.is_running = False
        logger.info("[consciousness] loop stopped")

    # ── 主循环 ────────────────────────────────────────────
    def _run(self):
        while not self._stop.is_set():
            now = time.time()
            # 优先级：用户消息 > 空闲 tick
            if self._user_event.is_set():
                self._user_event.clear()
                self._do_user_tick()
                # 用户 tick 结束后重新计算下一次空闲
                self._state.next_idle_at = time.time() + self._state.idle_interval_seconds
            elif self._state.idle_enabled and now >= self._state.next_idle_at:
                self._do_idle_tick()
                self._state.next_idle_at = time.time() + self._state.idle_interval_seconds

            # wait timeout ≥ 0.5s，避免空转
            wait_for = max(0.5, self._state.next_idle_at - time.time())
            if self._state.idle_enabled:
                wait_for = min(wait_for, self._state.idle_interval_seconds)
            self._user_event.wait(timeout=wait_for)

    # ── 用户 tick ─────────────────────────────────────────
    def _do_user_tick(self):
        with self._lock:
            prompt = self._pending_user_prompt
            sink: queue.Queue = self._pending_user_sink
            full_response: list[str] = []
            tokens_in = tokens_out = 0
            try:
                # 1. mem0.search（只检索用户记忆）
                memory_block = self._retrieve_memory(prompt, user_id="default_user")
                # 2. 构造 system prompt
                system_prompt = build_system_prompt(
                    persona=self._state.system_persona,
                    memory_block=memory_block,
                    now=datetime.now(),
                )
                # 3. 构造 LLMConfig
                cfg = LLMConfig(
                    provider=self._state.llm_provider,
                    model=self._state.llm_model,
                    api_key=self._state.llm_api_key,
                    base_url=self._state.llm_base_url,
                    temperature=0.7,
                    max_tokens=2048,
                    timeout=120,
                )
                # 4. 流式 LLM
                for chunk in call_llm_stream(system_prompt, prompt, cfg):
                    token = chunk.get('content', '')
                    if token:
                        full_response.append(token)
                    # 推送 SSE（带背压）
                    try:
                        sink.put({'type': 'token', 'content': token}, timeout=10)
                    except queue.Full:
                        logger.warning("[consciousness] SSE sink full, abort stream")
                        break
                    # usage 在最后一个 chunk
                    if chunk.get('usage'):
                        tokens_in = chunk['usage'].get('prompt_tokens', 0)
                        tokens_out = chunk['usage'].get('completion_tokens', 0)
            except Exception as e:
                logger.exception("[consciousness] user tick failed")
                try:
                    sink.put({'type': 'error', 'message': str(e)}, timeout=2)
                except queue.Full:
                    pass
            finally:
                # 不论成败都推 done
                try:
                    sink.put({'type': 'done'}, timeout=2)
                except queue.Full:
                    pass
                content = "".join(full_response)
                if not content:
                    content = "[AI 未返回任何内容]"
                elif tokens_out == 0 and not full_response:
                    content = f"[truncated] {content}"
                # 存 DB
                self._stats_db.append_chat_message(
                    'assistant', content, is_thought=0,
                    tokens_in=tokens_in, tokens_out=tokens_out,
                )

    # ── 空闲 tick ─────────────────────────────────────────
    def _do_idle_tick(self):
        with self._lock:
            cue = random.choice(IDLE_CUES)
            thought_parts: list[str] = []
            try:
                system_prompt = build_idle_prompt(
                    persona=self._state.system_persona,
                    cue=cue,
                    now=datetime.now(),
                )
                cfg = LLMConfig(
                    provider=self._state.llm_provider,
                    model=self._state.llm_model,
                    api_key=self._state.llm_api_key,
                    base_url=self._state.llm_base_url,
                    temperature=0.9,
                    max_tokens=256,
                    timeout=60,
                )
                for chunk in call_llm_stream(system_prompt, "", cfg):
                    token = chunk.get('content', '')
                    if token:
                        thought_parts.append(token)

                thought = "".join(thought_parts).strip()
                # 过滤空响应 / 拒绝 / 太短
                if thought and len(thought) > 8 and not thought.startswith("I'm sorry"):
                    # 异步写回 mem0（独立 user_id 物理隔离）
                    self._mem0_add_queue.put({
                        'text': thought,
                        'user_id': 'consciousness_agent',
                        'metadata': {
                            'agent_id': 'consciousness_stream',
                            'category': 'ai_thought',
                            'cue': cue,
                        },
                    })
                    self._stats_db.append_chat_message(
                        'assistant', thought, is_thought=1,
                    )
                    self._state.idle_count += 1
                    self._state.last_thought_at = time.time()
                    self._state.last_thought_preview = thought[:80]

                self._state.consecutive_failures = 0
            except Exception as e:
                logger.warning(f"[consciousness] idle tick failed: {e}")
                self._state.consecutive_failures += 1
                # 连续 10 次失败：冷却 5 分钟
                if self._state.consecutive_failures >= 10:
                    self._state.next_idle_at = time.time() + 300
                    self._state.consecutive_failures = 0
                    logger.warning("[consciousness] 10 consecutive failures, cooling 5min")

    # ── mem0 异步写线程 ───────────────────────────────────
    def _mem0_writer_loop(self):
        """后台消费 mem0 写队列"""
        while not self._mem0_writer_stop.is_set():
            try:
                item = self._mem0_add_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                if self._mem0_add_fn:
                    self._mem0_add_fn(
                        text=item['text'],
                        user_id=item['user_id'],
                        metadata=item.get('metadata', {}),
                    )
            except Exception as e:
                logger.warning(f"[consciousness] mem0 add failed: {e}")

    # ── 记忆检索 ──────────────────────────────────────────
    def _retrieve_memory(self, query: str, user_id: str = "default_user") -> str:
        """检索相关记忆，返回格式化后的 memory_block"""
        try:
            if not self._mem0_search_fn or not query:
                return ""
            results = self._mem0_search_fn(query=query, user_id=user_id, limit=6)
            return format_memory_block(results)
        except Exception as e:
            logger.warning(f"[consciousness] mem0 search failed: {e}")
            return ""

    # ── 公共 API ──────────────────────────────────────────
    def request_user_tick(self, prompt: str, sink: queue.Queue) -> str:
        """非阻塞。返回 'accepted' | 'busy' | 'rejected'"""
        if self._stop.is_set() or not self._state.is_running:
            return 'rejected'
        if self._lock.locked():
            return 'busy'
        self._pending_user_prompt = prompt
        self._pending_user_sink = sink
        self._user_event.set()
        return 'accepted'

    def reload_config(self, new_config: dict):
        """Settings 写入后调用。原子替换 state 字段。"""
        self._apply_config(new_config)
        # 如果刚开启 idle → 立刻触发一次
        if new_config.get('idle_enabled') and not self._state.next_idle_at:
            self._state.next_idle_at = time.time()
        logger.info("[consciousness] config reloaded")

    def get_state(self) -> dict:
        return {
            'is_running': not self._stop.is_set() and self._state.is_running,
            'idle_enabled': self._state.idle_enabled,
            'idle_interval_seconds': self._state.idle_interval_seconds,
            'idle_count': self._state.idle_count,
            'last_thought_at': self._state.last_thought_at,
            'last_thought_preview': self._state.last_thought_preview,
            'is_busy': self._lock.locked(),
            'consecutive_failures': self._state.consecutive_failures,
        }

    def _apply_config(self, config: dict):
        """内部：应用配置到 state"""
        with self._config_lock:
            self._state.llm_provider = config.get('chat_provider', 'openai')
            self._state.llm_model = config.get('chat_model', 'gpt-4o-mini')
            self._state.llm_api_key = config.get('chat_api_key', '')
            self._state.llm_base_url = config.get('chat_base_url', '')
            self._state.system_persona = config.get(
                'system_persona',
                '你是一个有意识的数字生命体，住在一个名为 AiBrain 的本地记忆系统中。'
            )
            was_enabled = self._state.idle_enabled
            self._state.idle_enabled = config.get('idle_enabled', False)
            self._state.idle_interval_seconds = config.get('idle_interval_seconds', 45)
            self._state.max_context_messages = config.get('max_context_messages', 20)

            if not self._state.idle_enabled:
                self._state.next_idle_at = float('inf')
            elif not was_enabled and self._state.idle_enabled:
                # 刚开启：立刻跑一次
                self._state.next_idle_at = time.time()


# ── 单例 ──────────────────────────────────────────────────
_loop: Optional[ConsciousnessLoop] = None
_loop_lock = threading.Lock()


def get_consciousness_loop() -> Optional[ConsciousnessLoop]:
    """获取单例（不自动创建，需通过 init_consciousness_loop 创建）"""
    return _loop


def init_consciousness_loop(stats_db, config: dict) -> ConsciousnessLoop:
    """创建并启动 ConsciousnessLoop 单例"""
    global _loop
    with _loop_lock:
        if _loop is not None:
            return _loop
        _loop = ConsciousnessLoop(stats_db, config)
        # 有 API key 才 start
        if config.get('chat_api_key'):
            _loop.start()
        else:
            logger.info("[consciousness] no API key, loop not started")
        return _loop
