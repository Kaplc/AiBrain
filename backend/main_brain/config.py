"""main_brain 配置集中管理（T000）

读取 ~/.aibrain/config/brain.json，缺字段用默认补。所有循环行为（session /
life / proactive）都可独立开关；max_cycles / timeout / cooldown / autonomy_level
集中在此，方便调试与降级。

设计：
  - 与 chat.json 同目录，单独文件避免污染现有 settings。
  - 只读快照 + 显式 reload，写操作留给 settings_routes（v1 不写回，先靠手动改文件）。
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger("main_brain.config")

# ── 默认配置 ─────────────────────────────────────────────────
DEFAULT_BRAIN = {
    # 总开关
    # session 默认关：开启后每次回复前会多跑 1-3 轮 judge LLM（增加延迟/成本）。
    # 第一版以兼容可回滚为优先（plan 设计前提 6 / FR-013），确认无碍后再手动打开。
    "brain_session_enabled": False,
    "life_loop_enabled": False,          # 常驻循环默认关，靠 /brain/life/start 启动
    "proactive_contact_enabled": False,  # 主动联系默认关，P6 再放量

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


def _config_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".aibrain", "config", "brain.json")


class BrainConfig:
    """main_brain 配置单例（只读快照 + reload）。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._data: dict = {}
        self.reload()

    @classmethod
    def get_instance(cls) -> "BrainConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def reload(self) -> None:
        """从磁盘重新加载，缺字段补默认。"""
        merged = dict(DEFAULT_BRAIN)
        path = _config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    merged.update(data)
            except Exception as e:
                logger.warning(f"[brain_config] load failed, using defaults: {e}")
        self._data = merged

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def as_dict(self) -> dict:
        return dict(self._data)

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


def ensure_default_config() -> None:
    """首次运行时写出默认 brain.json（若不存在）。供 app 启动时调用。"""
    path = _config_path()
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_BRAIN, f, indent=2, ensure_ascii=False)
        logger.info(f"[brain_config] wrote default config: {path}")
    except Exception as e:
        logger.warning(f"[brain_config] ensure_default_config failed: {e}")
