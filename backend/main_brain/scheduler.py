"""Scheduler — 生活节奏调度（T014 / FR-014）

单后台线程按短/中/长/每日节奏触发 LifeLoopDaemon.run_tick。
  short_tick  30s   不调 LLM（轻量）
  medium_tick 5min  选活动 + 轻量 judge
  long_tick   1h    整理记忆/lesson
  daily_tick  24h   日总结/目标回顾

用户正在聊天时降频：跳过 medium/long/daily（short 仍跑，维持 idle 跟踪）。
间隔来自 brain.json，可热改（reload 在 start 时读一次，运行中改文件需 stop/start）。
"""
from __future__ import annotations

import logging
import os
import threading

from .config import get_brain_config
from .contracts import TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY

# 项目根目录（用于日志路径）
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

logger = logging.getLogger("main_brain.scheduler")


class LifeScheduler:
    """生活节奏调度器单例。"""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._daemon = None
        self._clock = None  # 懒加载 BrainClock
        self._lock = threading.Lock()

    # ── 日志初始化 ───────────────────────────────────────────
    @staticmethod
    def _init_brain_log():
        """为 brain loop 创建独立的日志文件（logs/brain_*.log + 归档）。

        与 embed_server 模式一致：启动时归档旧日志，保留最新 3 份。
        brain 相关日志用独立文件，不与 flask 混在一起。
        """
        import time as _t
        log_dir = os.path.join(_PROJECT_ROOT, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # 归档旧的 brain 日志
        from core.logger import archive_logs
        archive_logs(log_dir, prefix="brain", keep=3)

        log_file = os.path.join(log_dir, f'brain_{_t.strftime("%Y%m%d_%H%M%S")}.log')
        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
        handler.setLevel(logging.INFO)

        # 只绑顶层 main_brain，子 logger（main_brain.daemon / .judge / .controller）
        # 默认 propagate 到父级 handler，不重复绑（避免每条日志写两次）
        logging.getLogger('main_brain').addHandler(handler)

        _lg = logging.getLogger('main_brain')
        _lg.info(f"[brain_log] writing to {log_file}")

    # ── 生命周期 ─────────────────────────────────────────────
    def start(self, *, daemon) -> dict:
        if self.is_running():
            return {"ok": True, "status": "already_running"}
        if not get_brain_config().life_loop_enabled:
            return {"ok": False, "status": "disabled",
                    "reason": "life_loop_enabled=False"}
        self._init_brain_log()
        self._daemon = daemon
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="LifeLoopScheduler", daemon=True)
        self._thread.start()
        logger.info("[scheduler] started")
        return {"ok": True, "status": "running"}

    def stop(self) -> dict:
        if not self.is_running():
            return {"ok": True, "status": "stopped"}
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=5)
        if self._clock is not None:
            self._clock.persist_on_stop()
        logger.info("[scheduler] stopped")
        return {"ok": True, "status": "stopped"}

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 主循环 ───────────────────────────────────────────────
    def _loop(self) -> None:
        # 延迟加载 BrainClock（scheduler 启动时才创建，不干扰模块加载阶段）
        if self._clock is None:
            from .clock import get_brain_clock
            self._clock = get_brain_clock()
        # 启动后先等一个短 tick，给系统预热时间
        self._sleep(get_brain_config().get("short_tick_seconds", 30))
        while not self._stop.is_set():
            cfg = get_brain_config()
            busy = _is_chat_busy()
            schedule = [
                (TICK_SHORT, int(cfg.get("short_tick_seconds", 30))),
                (TICK_MEDIUM, int(cfg.get("medium_tick_seconds", 300))),
                (TICK_LONG, int(cfg.get("long_tick_seconds", 3600))),
                (TICK_DAILY, 86400),
            ]
            for tick_type, interval in schedule:
                if self._stop.is_set():
                    break
                # 用户聊天时只保留 short
                if busy and tick_type != TICK_SHORT:
                    continue
                if self._clock.should_fire(tick_type, interval):
                    self._fire(tick_type)
                    self._clock.mark_fired(tick_type)
            # 以 short 间隔的较小值为心跳，避免空转过频
            self._sleep(min(15, max(5, int(cfg.get("short_tick_seconds", 30)) // 2)))

    def _fire(self, tick_type: str) -> None:
        if self._daemon is None:
            return
        try:
            self._daemon.run_tick(tick_type)
        except Exception as e:
            logger.warning(f"[scheduler] {tick_type} fire error: {e}")

    def _sleep(self, seconds: float) -> None:
        # 分段 sleep 以便及时响应 stop
        import time as _t
        end = _t.monotonic() + max(1, seconds)
        while not self._stop.is_set() and _t.monotonic() < end:
            _t.sleep(1)


def _is_chat_busy() -> bool:
    try:
        from modules.chat import ChatManager
        return bool(ChatManager.get_instance().get_status())
    except Exception:
        return False


_scheduler: LifeScheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> LifeScheduler:
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = LifeScheduler()
    return _scheduler
