"""BrainClock — 持久化大脑时钟（替代 time.monotonic() 的内存计时）

所有 tick 的最后触发时间以 ISO 时间戳存在 internal_state.json['brain_clock'] 节点，
重启后恢复，不会全部重新计时（避免 daily_tick 一重启就触发）。

设计：
  - 首次运行（无持久化数据）→ should_fire 返回 True（触一次后标记，下次正常）
  - 重启后 → 读磁盘恢复，按真实时间差判断是否该触
  - short_tick 只更新内存不写盘（30s 心跳，不需要持久化）
  - medium/long/daily 触发时写盘（频率低，不影响性能）
  - scheduler stop 时全量刷盘（保证退出时 checkpoint 最新）

外部访问：
    from main_brain.clock import get_brain_clock
"""
from __future__ import annotations

import logging
import threading

from .contracts import TICK_SHORT

logger = logging.getLogger("main_brain.clock")

_STATE_NODE = "brain_clock"


class BrainClock:
    """持久化大脑时钟单例。"""

    _instance = None
    _cls_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        # tick_type -> ISO timestamp（内存缓存）
        self._last_run_iso: dict[str, str] = {}
        self._dirty = False
        self._load()

    @classmethod
    def get_instance(cls) -> "BrainClock":
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 磁盘读写 ─────────────────────────────────────────────
    def _load(self) -> None:
        """从 internal_state.json 加载 brain_clock 节点到内存。"""
        try:
            from main_brain.state import get_state
            node = get_state().snapshot().get(_STATE_NODE)
            if isinstance(node, dict):
                times = node.get("last_run_times", {})
                if isinstance(times, dict):
                    self._last_run_iso = {str(k): str(v) for k, v in times.items()}
                    logger.info(f"[brain_clock] loaded: {self._last_run_iso}")
        except Exception as e:
            logger.warning(f"[brain_clock] load failed: {e}")

    def _persist(self) -> None:
        """把内存中的 last_run_times 写回 internal_state.json。"""
        if not self._dirty:
            return
        try:
            from main_brain.state import get_state
            with get_state().transaction() as data:
                data[_STATE_NODE] = data.get(_STATE_NODE, {})
                data[_STATE_NODE]["last_run_times"] = dict(self._last_run_iso)
            self._dirty = False
            logger.debug(f"[brain_clock] persisted: {self._last_run_iso}")
        except Exception as e:
            logger.warning(f"[brain_clock] persist failed: {e}")

    def persist_on_stop(self) -> None:
        """scheduler 停止时强制刷盘。"""
        with self._lock:
            self._dirty = True
        self._persist()

    # ── 核心接口 ─────────────────────────────────────────────
    def should_fire(self, tick_type: str, interval_seconds: int) -> bool:
        """检查距上次触发是否已过 interval。

        Args:
            tick_type: TICK_SHORT / TICK_MEDIUM / TICK_LONG / TICK_DAILY
            interval_seconds: brain.json 配置的对应间隔

        Returns:
            True 表示可以触发（未到间隔则 False）。
        """
        last_iso = self._last_run_iso.get(tick_type)
        if not last_iso:
            return True  # 首次运行（或新 tick 类型），需要触一次

        try:
            from main_brain.state import times
            from datetime import datetime, timezone
            last_dt = times.parse_iso(last_iso)
            if last_dt is None:
                return True  # 坏时间戳 → 重置
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            return elapsed >= interval_seconds
        except Exception as e:
            logger.warning(f"[brain_clock] should_fire error: {e}")
            return True  # 出错时放行（不阻断 tick）

    def mark_fired(self, tick_type: str) -> None:
        """记录当前时间为 tick_type 的最后触发时间。

        short_tick 只写内存（30s 心跳不写盘）；medium/long/daily 写盘。
        """
        from main_brain.state import times
        now = times.now_iso()
        with self._lock:
            self._last_run_iso[tick_type] = now
            self._dirty = True
        # short_tick 不写盘（频率高、不重要）
        if tick_type != TICK_SHORT:
            self._persist()

    def force_set(self, tick_type: str, iso: str) -> None:
        """强制设置某 tick 的最后触发时间（调试/手动修复用）。"""
        with self._lock:
            self._last_run_iso[tick_type] = iso
            self._dirty = True
        self._persist()

    def get_last_run(self, tick_type: str) -> str:
        """获取某 tick 最后触发时间的 ISO 字符串（空串 = 从未触发）。"""
        return self._last_run_iso.get(tick_type, "")

    def get_all_last_runs(self) -> dict:
        """返回所有 tick 的最后触发时间（只读快照）。"""
        with self._lock:
            return dict(self._last_run_iso)


def get_brain_clock() -> BrainClock:
    return BrainClock.get_instance()
