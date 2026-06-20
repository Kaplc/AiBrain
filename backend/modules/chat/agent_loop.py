"""
ConsciousnessLoop — 意识流守护线程
后台循环：空闲 tick（自由联想），用户交互不走此线程。
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

from modules.LLM import LLMConfig, get_llm_manager
from .prompts import (
    build_idle_prompt,
    IDLE_CUES,
)

logger = logging.getLogger(__name__)


@dataclass
class _LoopState:
    """意识流守护线程内部状态"""
    is_running: bool = False
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = ""
    system_persona: str = ""
    idle_enabled: bool = False
    idle_interval_seconds: int = 45
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
    """意识流守护线程（仅空闲思绪）"""

    def __init__(self, stats_db, config: dict):
        self._stats_db = stats_db
        self._state = _LoopState()
        self._lock = threading.Lock()
        self._config_lock = threading.Lock()
        self._stop = threading.Event()
        self._mem0_add_fn = None
        self._mem0_add_queue: queue.Queue = queue.Queue(maxsize=128)
        self._mem0_writer_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._apply_config(config)

    # ── mem0 注入 ─────────────────────────────────────────
    def set_mem0_add_fn(self, add_fn):
        self._mem0_add_fn = add_fn

    # ── 生命周期 ──────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._mem0_writer_stop.clear()
        self._state.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="consciousness-loop")
        self._thread.start()
        threading.Thread(target=self._mem0_writer_loop, daemon=True, name="mem0-writer").start()
        logger.info("[loop] started")

    def stop(self, timeout: float = 5.0):
        self._stop.set()
        self._mem0_writer_stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._state.is_running = False
        logger.info("[loop] stopped")

    # ── 主循环（仅空闲 tick） ────────────────────────────
    def _run(self):
        while not self._stop.is_set():
            now = time.time()
            if self._state.idle_enabled and now >= self._state.next_idle_at:
                self._do_idle_tick()
                self._state.next_idle_at = time.time() + self._state.idle_interval_seconds

            wait_for = max(0.5, self._state.next_idle_at - time.time())
            self._stop.wait(timeout=min(wait_for, 5.0))

    # ── 空闲 tick ─────────────────────────────────────────
    def _do_idle_tick(self):
        with self._lock:
            cue = random.choice(IDLE_CUES)
            thought_parts: list[str] = []
            try:
                system_prompt = build_idle_prompt(
                    persona=self._state.system_persona,
                    cue=cue, now=datetime.now(),
                )
                cfg = LLMConfig(
                    provider=self._state.llm_provider,
                    model=self._state.llm_model,
                    api_key=self._state.llm_api_key,
                    base_url=self._state.llm_base_url,
                    temperature=0.9, max_tokens=256, timeout=60,
                )
                for chunk in get_llm_manager().stream(system_prompt, "", cfg, source='idle_thought'):
                    token = chunk.get('content', '')
                    if token:
                        thought_parts.append(token)

                thought = "".join(thought_parts).strip()
                if thought and len(thought) > 8 and not thought.startswith("I'm sorry"):
                    self._mem0_add_queue.put({
                        'text': thought,
                        'user_id': 'consciousness_agent',
                        'metadata': {
                            'agent_id': 'consciousness_stream',
                            'category': 'ai_thought',
                            'cue': cue,
                        },
                    })
                    self._stats_db.append_chat_message('assistant', thought, is_thought=1)
                    self._state.idle_count += 1
                    self._state.last_thought_at = time.time()
                    self._state.last_thought_preview = thought[:80]

                self._state.consecutive_failures = 0
            except Exception as e:
                logger.warning(f"[loop] idle tick failed: {e}")
                self._state.consecutive_failures += 1
                if self._state.consecutive_failures >= 10:
                    self._state.next_idle_at = time.time() + 300
                    self._state.consecutive_failures = 0
                    logger.warning("[loop] 10 consecutive failures, cooling 5min")

    # ── mem0 异步写线程 ───────────────────────────────────
    def _mem0_writer_loop(self):
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
                logger.warning(f"[loop] mem0 add failed: {e}")

    # ── 公共 API ──────────────────────────────────────────
    def reload_config(self, new_config: dict):
        self._apply_config(new_config)
        if new_config.get('idle_enabled') and not self._state.next_idle_at:
            self._state.next_idle_at = time.time()
        logger.info("[loop] config reloaded")

    def get_state(self) -> dict:
        return {
            'is_running': not self._stop.is_set() and self._state.is_running,
            'idle_enabled': self._state.idle_enabled,
            'idle_interval_seconds': self._state.idle_interval_seconds,
            'idle_count': self._state.idle_count,
            'last_thought_at': self._state.last_thought_at,
            'last_thought_preview': self._state.last_thought_preview,
            'is_busy': False,
            'consecutive_failures': self._state.consecutive_failures,
        }

    def _apply_config(self, config: dict):
        with self._config_lock:
            self._state.llm_provider = config.get('provider', 'openai') or config.get('chat_provider', 'openai')
            self._state.llm_model = config.get('model', 'gpt-4o-mini') or config.get('chat_model', 'gpt-4o-mini')
            self._state.llm_api_key = config.get('api_key', '') or config.get('chat_api_key', '')
            self._state.llm_base_url = config.get('base_url', '') or config.get('chat_base_url', '')
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
                self._state.next_idle_at = time.time()
