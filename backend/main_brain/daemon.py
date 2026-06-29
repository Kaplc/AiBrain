"""LifeLoopDaemon — 常驻数字生命循环（T013）

意识流 tick：由 scheduler 定时触发 autonomous_mind.tick()，AI 自主决定做什么。
旧四种 tick（short/medium/long/daily）已废弃，ActivitySelector/registry 路径已移除。
start()/stop() 委托给 scheduler（T014）的后台线程。
"""
from __future__ import annotations

import logging

from .config import get_brain_config
from .contracts import BACKGROUND
from .logging.event_log import get_event_log

logger = logging.getLogger("main_brain.daemon")


class LifeLoopDaemon:
    """常驻生命循环。单例。"""

    def __init__(self):
        from .adapters.state import get_state_adapter
        from .adapters.expression import get_expression_adapter
        from .adapters.tools import get_tool_adapter
        self._state = get_state_adapter()
        self._expr = get_expression_adapter()
        self._tools = get_tool_adapter()
        self._scheduler = None  # 懒构造

    # ── 生命周期 ─────────────────────────────────────────────
    def start(self) -> dict:
        from .scheduler import get_scheduler
        self._scheduler = get_scheduler()
        return self._scheduler.start(daemon=self)

    def stop(self) -> dict:
        if self._scheduler is None:
            return {"ok": True, "status": "stopped"}
        res = self._scheduler.stop()
        self._scheduler = None
        return res

    def is_running(self) -> bool:
        from .scheduler import get_scheduler
        return get_scheduler().is_running()

    def run_alive_tick(self, *, dry_run: bool = False) -> dict:
        """意识流 tick：把完整上下文交给 AI，由它自己决定做什么。

        取代旧的四种 tick type。固定间隔由 scheduler 调用（consciousness_tick_seconds）。
        用户消息回复走独立 reactive 路径（session），不经此处。

        注意：旧的 short_tick 循环已废弃，idle_seconds 在此处实时计算。
        """
        life_state = self._state.read_life_state()
        # 实时计算 idle_seconds（short_tick 已废弃，不依赖它来累积）
        life_state["idle_seconds"] = self._compute_idle_seconds(life_state)

        # 发射 tick 开始事件
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "tick_started", {
                "tick_type": "consciousness",
                "idle_seconds": life_state.get("idle_seconds", 0),
                "life_loop_status": life_state.get("life_loop_status", ""),
            })
        except Exception:
            pass

        if not dry_run:
            self._state.set_loop_status("active_reflecting", activity="consciousness",
                                        focus=life_state.get("current_focus", ""))

        # 意识流决策（autonomous_mind 内循环）；tick 异常不阻断后续状态恢复
        from .autonomous_mind import get_autonomous_mind

        try:
            result = get_autonomous_mind().tick({"life_state": life_state, "dry_run": dry_run})
        except Exception as e:
            logger.exception(f"[daemon] consciousness tick crashed: {e}")
            result = {"action": "error", "thought": f"tick_error: {e}",
                      "cycle_count": 0, "tool_calls": 0, "llm_skipped": False}
        action = result.get("action", "rest")

        # 写入 tick 日志（持久化时间线）
        try:
            from .tick_log import record_tick
            record_tick("consciousness",
                        action=action,
                        cycles=result.get("cycle_count", 0),
                        llm_skipped=result.get("llm_skipped", False))
        except Exception:
            pass

        run_id = _new_run_id(BACKGROUND)

        # 写 brain_runs.jsonl
        if not dry_run:
            try:
                summary = {
                    "run_id": run_id,
                    "mode": BACKGROUND,
                    "trigger": {"tick_type": "consciousness"},
                    "started_at": _now(),
                    "finished_at": _now(),
                    "cycle_count": result.get("cycle_count", 0),
                    "selected_activity": action,
                    "actions": [action],
                    "stop_reason": action,
                    "last_error": "",
                    "thought_summary": str(result.get("thought", ""))[:200],
                }
                cycles = result.get("cycles", [])
                if cycles:
                    summary["cycles"] = cycles
                if result.get("output"):
                    summary["consciousness_output"] = str(result["output"])[:120]
                get_event_log().append_run(summary)
            except Exception as e:
                logger.warning(f"[daemon] consciousness log append failed: {e}")

        # 更新 LifeState
        if not dry_run:
            self._state.set_loop_status("idle_thinking", activity=action)
            self._state.update_life_node({
                "current_activity": action,
                "next_wake_hint": {"tick_type": "consciousness", "reason": "意识流 tick"},
            })
            # 保留：时间触发的记忆沉淀（旧 long/daily tick 触发已废弃）
            self._maybe_consolidate_consciousness()

        # 发射 tick 完成事件
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "tick_completed", {
                "tick_type": "consciousness",
                "activity": action,
                "stop_reason": action,
                "actions": [action],
                "cycle_count": result.get("cycle_count", 0),
                "llm_skipped": result.get("llm_skipped", False),
            })
        except Exception:
            pass

        logger.info(
            f"[consciousness] action={action} cycles={result.get('cycle_count', 0)} "
            f"tool_calls={result.get('tool_calls', 0)} "
            f"llm_skipped={result.get('llm_skipped', False)} "
            f"thought={str(result.get('thought', ''))[:60]}"
        )

        return {
            "ok": True,
            "run_id": run_id,
            "tick_type": "consciousness",
            "selected_activity": action,
            "consciousness": result,
            "stop_reason": action,
            "sent": bool(result.get("output")),
            "dry_run": dry_run,
        }

    def _maybe_consolidate_consciousness(self) -> None:
        """意识流 tick 的时间触发记忆沉淀。

        旧的 long_tick（每小时）/daily_tick（每天）是自动沉淀的唯一来源；意识流取代
        四种 tick 后，这里用 BrainClock 的时间门控保留这两个节奏，避免沉淀功能静默丢失。
        """
        try:
            from .consolidation import enqueue_consolidation, is_auto_trigger_enabled
            from .memory.consolidation import TRIGGER_IDLE_TICK, TRIGGER_DAILY_TICK
            from main_brain import clock as times
            from .clock import get_brain_clock
            cfg = get_brain_config()
            clock = get_brain_clock()
            for trigger, key, default_mins in (
                (TRIGGER_IDLE_TICK, "consolidation_idle",
                 cfg.get("consciousness_consolidate_idle_minutes", 60)),
                (TRIGGER_DAILY_TICK, "consolidation_daily",
                 cfg.get("consciousness_consolidate_daily_minutes", 1440)),
            ):
                if not is_auto_trigger_enabled(trigger):
                    continue
                interval_mins = float(default_mins)
                last = clock.get_last_run(key)
                if (not last) or (times.hours_since(last) * 60.0 >= interval_mins):
                    enqueue_consolidation(trigger)
                    clock.mark_fired(key)
                    logger.info(f"[daemon] consciousness consolidate enqueued: {trigger}")
        except Exception as e:
            logger.warning(f"[daemon] consciousness consolidate failed: {e}")

    def _compute_idle_seconds(self, life_state: dict) -> int:
        """读盘计算空闲秒数：tick_log → state → 0"""
        from .adapters.state import compute_idle_seconds
        return compute_idle_seconds(life_state)

def _new_run_id(mode: str) -> str:
    from main_brain import clock as times
    import hashlib
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    prefix = "br" if mode == "reactive" else "bg"
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:4]
    return f"{prefix}_{stamp}_{suffix}"


def _now() -> str:
    from main_brain import clock as times
    return times.now_iso()
