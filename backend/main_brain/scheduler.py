"""Scheduler — 意识流节奏调度

单后台线程按固定间隔（consciousness_tick_seconds，默认 30 分钟）触发
LifeLoopDaemon.run_alive_tick —— AI 自己决定此刻做什么（取代旧的
short/medium/long/daily 四种 tick + ActivitySelector 流水线）。

用户消息回复走独立 reactive 路径（session），不经此处；意识流 tick 不受用户
活跃度影响。两条路径并行，状态写经事务串行，speak 冷却防刷屏。

Day Tick / Sleep Tick:
  - Day Tick (醒): 读身份文件 + 环境 → 构建初始 Working Memory，触发 consolidation
  - Sleep Tick (睡): 沉淀 consolidation，清空 Working Memory
  两者都不调 LLM，纯调度层状态管理。
"""
from __future__ import annotations

import logging
import os
import threading

from .config import get_brain_config

# 项目根目录（用于日志路径）
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
_MAIN_BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))  # main_brain/ 目录

logger = logging.getLogger("main_brain.scheduler")


# ── 身份文件读取（模块级，不依赖实例）─────────────────────────────────
def _resolve_identity_path(fname: str) -> str:
    """解析身份文件绝对路径。支持相对（相对于 main_brain/）和绝对路径。"""
    cfg = get_brain_config()
    subdir = str(cfg.get("identity_dir", "prompts/identity"))
    if os.path.isabs(subdir):
        return os.path.normpath(os.path.join(subdir, fname))
    return os.path.normpath(os.path.join(_MAIN_BRAIN_DIR, subdir, fname))


def _read_identity_file(fname: str) -> str:
    """读身份文件内容。跳过空/脏数据（<5 字符）。"""
    try:
        path = _resolve_identity_path(fname)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content[:200] if len(content) >= 5 else ""
    except Exception:
        return ""


class LifeScheduler:
    """生活节奏调度器单例。"""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._daemon = None
        self._clock = None  # 懒加载 BrainClock
        self._lock = threading.Lock()
        self._last_day_tick_date: str = ""   # 上次 Day Tick 的日期（YYYY-MM-DD）
        # 睡眠会话 ID：每晚唯一（23:00-02:00 跨天区间视为同一"夜晚"）
        # 格式：若 now.hour >= 23 则使用当天日期，否则使用昨天日期
        self._last_sleep_session: str = ""
        self._last_alive_at: str = ""  # 上次 tick 完成后的时间戳（重启恢复靠 tick_log）
        self._sleep_mode: bool = False  # 深夜睡眠模式（sleep_tick 设 True，day_tick 清 False）
        self._woke_from_sleep: bool = False  # 本"夜"是否已被唤醒过（_sleep_tick 重置）

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

        # Sleep Tick：睡前仪式（无 LLM），沉淀 + 清空
        try:
            if get_brain_config().get("sleep_tick_enabled", True):
                self._sleep_tick(reason="scheduler_stop")
        except Exception as e:
            logger.warning(f"[scheduler] sleep_tick on stop failed: {e}")

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

    @property
    def sleep_mode(self) -> bool:
        """深夜睡眠模式。True 时意识流 tick 不调 LLM（除非用户消息唤醒）。"""
        return self._sleep_mode

    @sleep_mode.setter
    def sleep_mode(self, value: bool) -> None:
        self._sleep_mode = bool(value)

    # ── 主循环 ───────────────────────────────────────────────
    def _loop(self) -> None:
        """昼夜节律循环：Day Tick → 意识流 tick 循环 → Sleep Tick。

        睡眠模式下意识流 tick 完全暂停，只轮询用户消息。
        用户发消息 → 重建上下文 + 唤醒 AI → 正常回复 → 无回复则自然睡回去。
        """
        if self._clock is None:
            from .clock import get_brain_clock
            self._clock = get_brain_clock()
        cfg = get_brain_config()

        # 启动后先等一个短预热，再开始第一次意识流 tick
        self._sleep(min(60, max(15, int(cfg.get("short_tick_seconds", 30)))))

        # Day Tick：构建初始 Working Memory（启动时不触发 consolidation，避免每次重启都整理记忆）
        if cfg.get("day_tick_enabled", True):
            self._day_tick(consolidate=False)

        # 重启检测：如果在清晨 day_tick 之前，补设睡眠模式
        # （重启后 _sleep_mode 默认 False，而 _maybe_sleep_tick 在
        #  深夜 deep night 窗口 23-02 过去后就不再触发，需要这里补）
        if cfg.get("sleep_tick_enabled", True) and not self._sleep_mode:
            _h = self._clock.local_hour()
            _day_start = int(cfg.get("day_tick_hour_start", 6))
            if 0 <= _h < _day_start:
                logger.info(f"[scheduler] startup at h={_h} before day_tick ({_day_start}), "
                            f"entering sleep mode")
                self._sleep_tick(reason="restart_during_sleep_hours")

        from .autonomous_mind import get_autonomous_mind

        while not self._stop.is_set():
            # ── 睡眠模式：意识流 tick 完全暂停 ──
            if self._sleep_mode:
                if get_autonomous_mind().has_pending_messages:
                    logger.info("[scheduler] 🔔 wake signal: pending message detected")
                    # 首次唤醒：重建上下文（身份 + 环境 + 睡眠感知）
                    if not self._woke_from_sleep:
                        logger.info("[scheduler] 🌅 first wake this night: rebuilding context")
                        self._wake_context()
                        self._woke_from_sleep = True
                    # 执行一次 tick 处理用户消息，完成后自然睡回去
                    self._alive_tick()
                    self._last_alive_at = self._clock.now_iso_local()
                    logger.info("[scheduler] 🌙 wake tick done, returning to sleep poll")
                else:
                    logger.debug("[scheduler] 💤 sleep poll: 60s wait for message")
                    self._sleep(60)

                if self._stop.is_set():
                    break
                # 昼夜节律检查（维持 tick_log 连续性，day_tick 负责清除睡眠标记）
                try:
                    if cfg.get("sleep_tick_enabled", True):
                        self._maybe_sleep_tick()
                    if cfg.get("day_tick_enabled", True):
                        self._maybe_day_tick()
                except Exception:
                    pass
                continue

            # ── 正常清醒模式 ──
            self._alive_tick()
            if self._stop.is_set():
                break

            # 有用户消息待处理 → 不 sleep，立即下一轮
            try:
                if get_autonomous_mind().has_pending_messages:
                    continue
            except Exception:
                pass

            # 检查是否需要 Sleep Tick（深夜时段）
            if cfg.get("sleep_tick_enabled", True):
                self._maybe_sleep_tick()

            # 检查是否需要再次 Day Tick（跨天了）
            if cfg.get("day_tick_enabled", True):
                self._maybe_day_tick()

            # 根据上次 tick 时间计算剩余间隔 sleep（重启后延续之前的节奏）
            self._sleep_until_next_alive()

            # 记录本轮 tick 完成时间（供下次 sleep 计算）
            self._last_alive_at = self._clock.now_iso_local()

    def _alive_tick(self) -> None:
        """一次意识流 tick。"""
        if self._daemon is None:
            return
        try:
            self._daemon.run_alive_tick()
        except Exception as e:
            logger.warning(f"[scheduler] alive_tick error: {e}")

    def _sleep_until_next_alive(self) -> None:
        """根据上次 tick 完成时间计算剩余间隔再 sleep。

        优先用 _last_alive_at（内存），为空时从 tick_log.json 恢复（重启）。
        重启时 tick_log 有重启前的记录 → 只 sleep 剩余部分，延续之前节奏。
        """
        interval = int(get_brain_config().get("consciousness_tick_seconds", 1800))
        last_ts = self._last_alive_at
        if not last_ts:
            # 重启后内存为空，从 tick_log 恢复
            try:
                from .tick_log import last_tick_iso
                last_ts = last_tick_iso("consciousness")
            except Exception:
                pass
        if last_ts:
            try:
                from datetime import datetime
                last_dt = datetime.fromisoformat(last_ts)
                elapsed = (datetime.now() - last_dt).total_seconds()
                remaining = max(1, interval - elapsed)
                logger.debug(f"[scheduler] alive interval: {elapsed:.0f}s elapsed, "
                             f"{remaining:.0f}s remaining")
                self._sleep(int(remaining))
                return
            except Exception as e:
                logger.warning(f"[scheduler] compute alive interval failed: {e}")
        # 兜底：无记录或出错时睡满间隔
        self._sleep(interval)

    # ── 昼夜节律 ─────────────────────────────────────────────
    def _day_tick(self, *, consolidate: bool = True) -> dict:
        """Day Tick：醒来仪式（无 LLM）。

        读身份文件 + 环境信息 → 构建初始 Working Memory。
        清空 internal_dialogue，触发每日记忆 consolidation。

        Args:
            consolidate: 是否触发每日记忆 consolidation。启动时重建 WM 传 False，
                        避免每次重启都触发整理。清晨自然触发时才传 True。
        """
        wm = []

        # 1. 读 Prompt 身份文件（AI 可编辑，>5 字符有效）
        for fname in ("self.md", "goals.md", "open_loops.md"):
            content = _read_identity_file(fname)
            if content:
                wm.append(content)

        # 2. 环境信息（时间 / 用户状态）
        wm.extend(self._scan_environment())

        # 3. 写 Working Memory + 清空 internal_dialogue
        from .adapters.state import get_state_adapter
        state = get_state_adapter()
        state.replace_working_memory(wm)

        def _clear(stream):
            stream["internal_dialogue"] = []
        state.mutate_stream(_clear)

        # 4. 记录日期
        from .clock import get_brain_clock
        self._last_day_tick_date = get_brain_clock().today_str()

        # 5. 退出睡眠模式（新的一天，正式醒来）
        if self._sleep_mode:
            self._sleep_mode = False
            self._last_alive_at = self._clock.now_iso_local()
            logger.info("[scheduler] sleep_mode cleared by day_tick")

        # 6. 写入 tick 日志
        try:
            from .tick_log import record_tick
            record_tick("day_tick", wm_count=len(wm))
        except Exception:
            pass

        # 7. 触发每日 consolidation（只在天亮自然触发时执行，重启时跳过）
        if consolidate:
            self._enqueue_consolidation("daily")

        logger.info(f"[scheduler] day_tick done: {len(wm)} wm items"
                    + ("" if consolidate else " (no consolidation)"))
        return {"ok": True, "wm_count": len(wm)}

    def _maybe_day_tick(self) -> None:
        """跨天检测：日期变化且处于清晨时段时再次触发 Day Tick。"""
        from .clock import get_brain_clock
        clock = get_brain_clock()
        cfg = get_brain_config()
        h = clock.local_hour()
        day_start = int(cfg.get("day_tick_hour_start", 6))
        day_end = int(cfg.get("day_tick_hour_end", 8))
        # 只在清晨时段（默认 6:00-8:00）触发 Day Tick
        if not (day_start <= h < day_end):
            return
        today = clock.today_str()
        if today != self._last_day_tick_date:
            logger.info(f"[scheduler] day changed {self._last_day_tick_date} -> {today}")
            self._day_tick()
        elif self._sleep_mode:
            # 睡眠模式下 day_tick 必须 firing 来清除标记
            # （重启后 startup day_tick 已设 _last_day_tick_date，导致
            #  上方日期比较不成立，但 sleep_mode 还未被清除）
            logger.info(f"[scheduler] day_tick forced (sleep_mode=True, date={today})")
            self._day_tick()

    def _sleep_tick(self, *, reason: str = "deep_night") -> dict:
        """Sleep Tick：睡前仪式（无 LLM）。

        触发 consolidation + 清空 Working Memory。

        Args:
            reason: 触发原因（"deep_night" / "scheduler_stop" / "restart_during_sleep_hours"）
        """
        from .adapters.state import get_state_adapter
        state = get_state_adapter()

        # 1. 触发记忆 consolidation（重启检测时跳过，避免每次重启都整理）
        if reason != "restart_during_sleep_hours" and get_brain_config().get("sleep_tick_consolidate", True):
            self._enqueue_consolidation("idle")

        # 2. 清空 Working Memory
        state.clear_working_memory()

        # 3. 写入 tick 日志
        try:
            from .tick_log import record_tick
            record_tick("sleep_tick", reason=reason)
        except Exception:
            pass

        # 4. 记录睡眠会话（防跨天重复触发）
        from .clock import get_brain_clock
        clock = get_brain_clock()
        # 深夜 23:00-02:00 视为同一"夜晚"：23 点后 session 用当天日期，0-2 点用昨天
        if clock.local_hour() >= 23:
            self._last_sleep_session = clock.today_str()
        else:
            from datetime import timedelta
            self._last_sleep_session = (clock.now_local() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 进入睡眠模式：意识流 tick 完全暂停，用户消息可唤醒
        self._sleep_mode = True
        self._woke_from_sleep = False  # 新一晚，还未被唤醒过
        logger.info(f"[scheduler] sleep_mode=True (reason={reason})")

        logger.info(f"[scheduler] sleep_tick done (reason={reason})")
        return {"ok": True, "reason": reason}

    def _maybe_sleep_tick(self) -> None:
        """深夜检测：23:00-02:00 时触发 Sleep Tick（每"夜"最多一次）。"""
        from datetime import timedelta
        from .clock import get_brain_clock
        from .config import get_brain_config
        clock = get_brain_clock()
        cfg = get_brain_config()
        h = clock.local_hour()
        sleep_start = int(cfg.get("sleep_tick_hour_start", 23))
        sleep_end = int(cfg.get("sleep_tick_hour_end", 2))
        # 跨天判断：如 sleep_start=23, sleep_end=2, 则条件为 h >= 23 or h < 2
        if sleep_start > sleep_end:
            is_deep_night = h >= sleep_start or h < sleep_end
        else:
            is_deep_night = sleep_start <= h < sleep_end
        if not is_deep_night:
            return
        # 构造"夜晚 session ID"——跨天统一归到起始日的日期
        if h >= sleep_start:
            session = clock.today_str()
        else:
            session = (clock.now_local() - timedelta(days=1)).strftime("%Y-%m-%d")
        if session == self._last_sleep_session:
            return  # 这一晚已经睡过
        logger.info(f"[scheduler] deep night detected, running sleep_tick")
        self._sleep_tick(reason="deep_night")

    def _wake_context(self) -> None:
        """从睡眠中唤醒：重建 Working Memory + 注入睡眠感知。

        类似 Day Tick 的身份文件读取流程，但追加"被唤醒"标记，
        让 AI 在下一轮 tick 中感知自己刚被从睡梦中叫醒。
        """
        wm = []
        for fname in ("self.md", "goals.md", "open_loops.md"):
            content = _read_identity_file(fname)
            if content:
                wm.append(content)
        wm.extend(self._scan_environment())
        wm.append("被志远从睡梦中唤醒了")

        from .adapters.state import get_state_adapter
        state = get_state_adapter()
        state.replace_working_memory(wm)

        def _wake_fn(stream):
            stream["internal_dialogue"] = []
            stream["last_thought"] = "（刚从睡梦中被志远唤醒）"
        state.mutate_stream(_wake_fn)

        logger.info("[scheduler] wake_context: user message woke me from sleep")

    def _scan_environment(self) -> list[str]:
        """打包环境信息：日期、时段、用户活跃度、最后聊天。

        对于数字生命体，"环境" = 系统内部状态。没有传感器，
        只是把已有的时间/用户状态信息整理成文本。
        """
        env = []
        from .clock import get_brain_clock
        clock = get_brain_clock()
        local_now = clock.now_local()
        weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四",
                       4: "周五", 5: "周六", 6: "周日"}
        env.append(f"今天是{weekday_map[local_now.weekday()]}，{clock.time_of_day_label()}")

        # 用户活跃度
        try:
            from .adapters.state import get_state_adapter
            life = get_state_adapter().read_life_state()
            idle = int(life.get("idle_seconds", 0) or 0)
            if idle < 60:
                env.append("志远刚还在")
            elif idle < 1800:
                env.append(f"志远已经离开{idle // 60}分钟了")
            else:
                env.append(f"志远已经离开{idle // 3600}小时了")
        except Exception:
            pass

        # 最后聊天内容
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            if entries:
                last = entries[-1]
                user_part = last.get("user", "")
                if user_part:
                    env.append(f"最后聊到：{str(user_part)[:60]}")
        except Exception:
            pass

        return env

    def _enqueue_consolidation(self, trigger_type: str) -> None:
        """触发后台记忆 consolidation（不阻塞当前线程）。"""
        try:
            from .consolidation import enqueue_consolidation, is_auto_trigger_enabled
            if trigger_type == "daily":
                from .memory.consolidation import TRIGGER_DAILY_TICK
                if is_auto_trigger_enabled(TRIGGER_DAILY_TICK):
                    enqueue_consolidation(TRIGGER_DAILY_TICK)
            elif trigger_type == "idle":
                from .memory.consolidation import TRIGGER_IDLE_TICK
                if is_auto_trigger_enabled(TRIGGER_IDLE_TICK):
                    enqueue_consolidation(TRIGGER_IDLE_TICK)
        except Exception as e:
            logger.warning(f"[scheduler] enqueue consolidation failed: {e}")

    def _sleep(self, seconds: float) -> None:
        # 分段 sleep 以便及时响应 stop 和用户消息
        import time as _t
        end = _t.monotonic() + max(1, seconds)
        while not self._stop.is_set() and _t.monotonic() < end:
            _t.sleep(1)
            # 有用户消息待处理 → 提前醒来
            try:
                from .autonomous_mind import get_autonomous_mind
                if get_autonomous_mind().has_pending_messages:
                    logger.info(f"[scheduler] sleep interrupted by pending message "
                                f"({seconds:.0f}s timer, {end - _t.monotonic():.0f}s remaining)")
                    break
            except Exception:
                pass


_scheduler: LifeScheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> LifeScheduler:
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = LifeScheduler()
    return _scheduler
