"""main_brain 配置集中管理（全部由 py 文件定义）

所有循环行为（session / life / proactive）通过 DEFAULT_BRAIN 常量配置，
直接修改 config.py 后重启后端生效。不读外部文件，不依赖 C 盘 brain.json。
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger("main_brain.config")

# ── 默认配置 ─────────────────────────────────────────────────
DEFAULT_BRAIN = {
    # 总开关
    # session 默认关：开启后每次回复前会多跑 1-3 轮 judge LLM（增加延迟/成本）。
    # 第一版以兼容可回滚为优先（plan 设计前提 6 / FR-013），确认无碍后再手动打开。
    "brain_session_enabled": False,
    "life_loop_enabled": False,          # 常驻循环默认关，靠 /brain/life/start 启动
    "proactive_contact_enabled": False,

    # Reactive BrainSession
    "brain_session_max_cycles": 3,       # 可配到 5
    "brain_session_timeout_seconds": 60,
    "judge_timeout_seconds": 20,

    # LifeLoop 节奏
    "short_tick_seconds": 30,
    "medium_tick_seconds": 300,
    "long_tick_seconds": 3600,
    "short_tick_max_cycles": 0,          # short_tick 默认不调 LLM
    "medium_tick_max_cycles": 2,
    "long_tick_max_cycles": 2,
    "daily_tick_max_cycles": 3,
    "background_tick_timeout_seconds": 30,

    # 自主等级 / 预算
    "autonomy_level": "assist",          # observe / assist / autonomous / high_autonomy
    "judge_temperature": 0.3,

    # 主动表达闸门
    "proactive_value_threshold": 0.65,
    "proactive_interruption_max": 0.35,
    "proactive_cooldown_minutes": 30,
    "proactive_repetition_max": 0.6,

    # 输出记忆沉淀（memory_consolidation）
    # 总开关默认关：自动沉淀会调 LLM + 写长时记忆，确认无碍后再打开。manual 接口始终可用。
    "memory_consolidation_enabled": False,
    "memory_consolidation_daily_tick": False,    # 日 tick 沉淀
    "memory_consolidation_window_size": 20,      # 单次扫描窗口
}


# 统一事件回路开关（代码常量）
EVENT_ORCHESTRATOR_ENABLED = True


class BrainConfig:
    """main_brain 配置单例 — 全部从 py 常量读取，不依赖外部文件。"""

    _instance = None
    _lock = threading.Lock()

    # 运行时聊天模式：brain_first / fallback（不持久化，进程级，重启恢复为 brain_first）
    CHAT_MODE_BRAIN_FIRST = "brain_first"
    CHAT_MODE_FALLBACK = "fallback"

    def __init__(self):
        self._data = dict(DEFAULT_BRAIN)
        self._chat_mode: str = self.CHAT_MODE_BRAIN_FIRST
        self._chat_mode_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "BrainConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def as_dict(self) -> dict:
        return dict(self._data)

    # ── 运行时聊天模式 ─────────────────────────────────────
    def get_chat_mode(self) -> str:
        with self._chat_mode_lock:
            return self._chat_mode

    def set_chat_mode(self, mode: str) -> None:
        if mode not in (self.CHAT_MODE_BRAIN_FIRST, self.CHAT_MODE_FALLBACK):
            raise ValueError(f"无效聊天模式: {mode}")
        with self._chat_mode_lock:
            self._chat_mode = mode

    # ── 常用便捷取值 ─────────────────────────────────────────
    @property
    def session_enabled(self) -> bool:
        return bool(self._data.get("brain_session_enabled", True))

    @property
    def life_loop_enabled(self) -> bool:
        return bool(self._data.get("life_loop_enabled", False))

    @property
    def proactive_enabled(self) -> bool:
        return bool(self._data.get("proactive_contact_enabled", False))

    @property
    def autonomy_level(self) -> str:
        return self._data.get("autonomy_level", "assist")


def get_brain_config() -> BrainConfig:
    """获取 BrainConfig 单例。"""
    return BrainConfig.get_instance()
