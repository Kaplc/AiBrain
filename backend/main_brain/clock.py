"""BrainClock — 统一时间模块（持久化时钟 + UTC/本地时间工具）

合并了原 state/times.py 的所有功能，作为整个 main_brain 唯一的时间入口。

职责：
  - UTC 时间：now() / parse_iso() / hours_since() / days_since() 等纯函数
  - 本地时间：now_local() / today_str() / time_of_day_label() 等
  - 持久化 tick 计时：should_fire() / mark_fired() 管理各 tick 的触发间隔

外部访问：
    from main_brain.clock import get_brain_clock, now, hours_since
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta

from .contracts import TICK_SHORT

logger = logging.getLogger("main_brain.clock")

_STATE_NODE = "brain_clock"


# ── UTC 纯函数（原 state/times.py，合并至此）───────────────────
def now() -> datetime:
    """当前 UTC 时间（持久化 / hours_since 等计算用）。"""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def parse_iso(ts: str) -> datetime | None:
    """解析 ISO 时间字符串；无时区视作 UTC；失败返回 None。"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_since(ts: str) -> float:
    """距 ts 的天数（float）。无/坏时间戳返回大数（视为很久以前）。"""
    dt = parse_iso(ts)
    if dt is None:
        return 9999.0
    return max(0.0, (now() - dt).total_seconds() / 86400.0)


def hours_since(ts: str) -> float:
    dt = parse_iso(ts)
    if dt is None:
        return 9999.0
    return max(0.0, (now() - dt).total_seconds() / 3600.0)


def now_plus_hours_iso(hours: float) -> str:
    """now + hours 后的 ISO 字符串（用于 expire_at / refractory_until）。"""
    return (now() + timedelta(hours=hours)).isoformat()


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
            last_dt = parse_iso(last_iso)
            if last_dt is None:
                return True  # 坏时间戳 → 重置
            elapsed = (now() - last_dt).total_seconds()
            return elapsed >= interval_seconds
        except Exception as e:
            logger.warning(f"[brain_clock] should_fire error: {e}")
            return True  # 出错时放行（不阻断 tick）

    def mark_fired(self, tick_type: str) -> None:
        """记录当前时间为 tick_type 的最后触发时间。

        short_tick 只写内存（30s 心跳不写盘）；medium/long/daily 写盘。
        """
        with self._lock:
            self._last_run_iso[tick_type] = now_iso()
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

    # ── 本地时间（统一入口，方便测试/替换）──────────────────
    @staticmethod
    def now_local() -> datetime:
        """当前本地系统时间（昼夜节律检测、日志用）。"""
        from datetime import datetime
        return datetime.now()

    @staticmethod
    def now_iso_local() -> str:
        return BrainClock.now_local().isoformat()

    @staticmethod
    def today_str() -> str:
        """今天日期 YYYY-MM-DD（本地时间）。"""
        return BrainClock.now_local().strftime("%Y-%m-%d")

    @staticmethod
    def local_hour() -> int:
        """当前小时（本地时间，24h）。"""
        return BrainClock.now_local().hour

    @staticmethod
    def time_of_day_label(h: int | None = None) -> str:
        """时段标签：黎明/上午/中午/下午/晚上/深夜。默认用当前本地小时。"""
        if h is None:
            h = BrainClock.local_hour()
        if 5 <= h < 8:
            return "黎明"
        if 8 <= h < 12:
            return "上午"
        if 12 <= h < 14:
            return "中午"
        if 14 <= h < 18:
            return "下午"
        if 18 <= h < 23:
            return "晚上"
        return "深夜"


def get_brain_clock() -> BrainClock:
    return BrainClock.get_instance()
