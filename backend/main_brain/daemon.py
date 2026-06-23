"""LifeLoopDaemon — 常驻数字生命循环（T013）

用户无输入时维持自己的节奏。run_tick(tick_type) 是单次闭环（plan 第七节 tick 固定
读写契约）：读固定上下文 → ActivitySelector 选活动 → BrainJudge 决策 → adapter 执行
→ 表达闸门 → 写 TickOutput → 更新 LifeState → 记 brain_runs.jsonl。

start()/stop() 委托给 scheduler（T014）的后台线程。短 tick 不调 LLM（性能验收 #1）。
用户正在聊天时降低频率（非功能 #5）。
"""
from __future__ import annotations

import logging

from .config import get_brain_config
from .contracts import (
    BACKGROUND, BrainRun, BrainRunContext,
    TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY, TICK_MANUAL,
)
from .logging.event_log import get_event_log

logger = logging.getLogger("main_brain.daemon")


# 各 tick 的默认 LLM 轮数
_TICK_MAX_CYCLES = {
    TICK_SHORT: "short_tick_max_cycles",
    TICK_MEDIUM: "medium_tick_max_cycles",
    TICK_LONG: "long_tick_max_cycles",
    TICK_DAILY: "daily_tick_max_cycles",
    TICK_MANUAL: "medium_tick_max_cycles",
}


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

    # ── 单次 tick ───────────────────────────────────────────
    def run_tick(self, tick_type: str = TICK_MEDIUM, *, dry_run: bool = False,
                 activity_override: str | None = None) -> dict:
        """执行一次 life tick。Returns: TickOutput 摘要 dict。"""
        cfg = get_brain_config()
        max_cycles = int(cfg.get(_TICK_MAX_CYCLES.get(tick_type, "medium_tick_max_cycles"), 0))
        timeout = float(cfg.get("background_tick_timeout_seconds", 30))

        # 1. 读固定上下文 → TickInput
        tick_input = self._build_tick_input(tick_type)
        life_state = tick_input.life_state

        # 短 tick：更新 idle/energy/status，不调 LLM
        if tick_type == TICK_SHORT:
            return self._run_short_tick(life_state, dry_run)

        # 2. ActivitySelector 选活动
        from .activity_selector import get_activity_selector
        selector = get_activity_selector()
        activity, reason = selector.select(
            life_state, tick_type,
            recent_runs=tick_input.recent_runs,
            pending_expressions=tick_input.pending_expressions,
            autonomy_level=cfg.autonomy_level,
        )
        if activity_override:
            activity = activity_override

        # 3. build run context (mode=background)
        run = BrainRun(
            run_id=_new_run_id(BACKGROUND),
            mode=BACKGROUND,
            trigger={"tick_type": tick_type, "tick_id": tick_input.tick_id},
            started_at=_now(),
            selected_activity=activity,
        )
        ctx = BrainRunContext(
            run=run,
            life_state=life_state,
            trigger=run.trigger,
            tick_type=tick_type,
            selected_activity=activity,
            memory_context=list(tick_input.memory_digest.get("items", []) or []),
            pending_expressions=tick_input.pending_expressions,
            config={"_state_adapter": self._state},
            budgets={"max_tools": 1},
        )

        # 4. 状态切到 active_reflecting
        if not dry_run:
            self._state.set_loop_status("active_reflecting", activity=activity,
                                        focus=life_state.get("current_focus", ""))

        logger.info(
            f"[tick] {tick_type} activity={activity} cycles={max_cycles} "
            f"reason={reason[:60]}"
        )

        # 5a. reflect 活动特殊处理：直接调反思核心，不走 LLM controller
        if activity == "reflect" and not dry_run:
            return self._run_reflect_activity(run, tick_type, reason, tick_input)

        # 5b. controller 跑循环（其他活动）
        stop_reason = "max_cycles"
        try:
            from .controller import get_cycle_runner
            stop_reason = get_cycle_runner().run(
                ctx, max_cycles=max_cycles, timeout_seconds=timeout,
                budgets=ctx.budgets, dry_run=dry_run,
            )
            run.finished_at = _now()
        except Exception as e:
            logger.exception(f"[daemon] tick {tick_type} failed: {e}")
            stop_reason = "error"
            run.stop_reason = stop_reason
            if not dry_run:
                self._state.set_error(str(e))

        # 汇总：actions + 想法摘要
        actions_summary = [c.action for c in run.cycles]
        thought = run.cycles[-1].thought_summary if run.cycles else reason
        logger.info(
            f"[tick] done {tick_type} actions={actions_summary} "
            f"stop={stop_reason} cycles={len(run.cycles)} "
            f"thought={thought}"
        )

        # 6. 表达闸门（有 pending 且活动相关才评估）
        # 重新读取 pending（包含本轮 judge 刚创建的），不像 tick_input 只取 tick 开始时的
        gate_out = {}
        if not dry_run and activity in ("proactive_contact", "prepare_expression", "reflect"):
            current_pending = self._expr._pending().get_unexpressed()
            if current_pending:
                try:
                    gate_out = self._expr.evaluate_and_send(
                        self._state.read_life_state(),
                        chat_busy=_is_chat_busy(),
                        recent_messages=tick_input.recent_assistant_messages,
                    )
                except Exception as e:
                    logger.warning(f"[daemon] expression eval failed: {e}")

        # 7. 写 TickOutput + 更新 life 状态 + 记日志
        thought = run.cycles[-1].thought_summary if run.cycles else reason
        # 沉淀本轮 learning_hints（后台学习，FR-010）
        if not dry_run and run.learning_hints:
            try:
                from .adapters.learning import get_learning_adapter
                get_learning_adapter().sink_hints(
                    run.learning_hints, thought=thought,
                    focus=life_state.get("current_focus", ""), source="life_tick")
            except Exception as e:
                logger.warning(f"[daemon] sink learning_hints failed: {e}")
        summary = run.to_summary()
        summary["thought_summary"] = thought[:200]
        try:
            get_event_log().append_run(summary, full=run.to_full())
        except Exception as e:
            logger.warning(f"[daemon] log append failed: {e}")
        if not dry_run:
            self._state.set_loop_status("idle_thinking", activity="wait")
            self._state.update_life_node({
                "current_activity": activity,
                "next_wake_hint": {"tick_type": _next_tick(tick_type), "reason": reason},
            })

        return {
            "run_id": run.run_id,
            "tick_type": tick_type,
            "selected_activity": activity,
            "reason": reason,
            "cycle_count": len(run.cycles),
            "actions": summary.get("actions", []),
            "stop_reason": stop_reason,
            "thought_summary": thought[:160],
            "gate": gate_out.get("gate", {}),
            "sent": gate_out.get("sent", False),
            "dry_run": dry_run,
        }

    def _run_short_tick(self, life_state: dict, dry_run: bool) -> dict:
        """短 tick：只更新 idle_seconds / energy / status，不调 LLM。"""
        if dry_run:
            return {"tick_type": TICK_SHORT, "selected_activity": "wait", "dry_run": True}
        idle = self._compute_idle_seconds(life_state)
        energy = self._compute_energy(life_state, idle)
        pending_count = len(life_state.get("pending_expressions", []) or [])
        self._state.update_life_node({
            "idle_seconds": idle,
            "energy": energy,
            "life_loop_status": "idle_thinking",
            "current_activity": "wait",
        })
        open_loops_count = len(life_state.get("open_loops", []) or [])
        thoughts_count = len(life_state.get("recent_thoughts", []) or [])
        mood = life_state.get("mood", {}) or {}
        last_user_contact = life_state.get("last_user_contact_at", "")[-19:-10] if life_state.get("last_user_contact_at") else ""

        logger.info(
            f"[heartbeat] idle={idle}s energy={energy:.2f} "
            f"pending={pending_count} loops={open_loops_count} "
            f"thoughts={thoughts_count} focus={life_state.get('current_focus','')[:20]}"
            f" mood={mood.get('label','')} valence={mood.get('valence',0)} "
            f"arousal={mood.get('arousal',0)}"
            f" last_contact={last_user_contact}"
        )
        return {
            "tick_type": TICK_SHORT,
            "selected_activity": "wait",
            "idle_seconds": idle,
            "energy": round(energy, 3),
            "stop_reason": "sleep",
        }

    def _run_reflect_activity(self, run, tick_type: str, reason: str, tick_input) -> dict:
        """reflect 活动：直接调用反思核心，不走 LLM BrainJudge。

        Returns: 同 run_tick 的标准返回格式。
        """
        reflect_result = {"ok": False, "skipped": True, "reason": "not executed",
                          "updated_fields": [], "summary": ""}
        try:
            from main_brain.narrative import get_self_narrative
            store = get_self_narrative()
            if store is None:
                reflect_result = {"ok": False, "skipped": True, "reason": "narrative store not ready",
                                  "updated_fields": [], "summary": ""}
            else:
                from main_brain.reflection import run_reflection
                reflect_result = run_reflection(store, force=False)
        except Exception as e:
            logger.warning(f"[daemon] reflect activity failed: {e}")
            reflect_result = {"ok": False, "skipped": True, "reason": str(e),
                              "updated_fields": [], "summary": ""}

        # 用反思结果构造 BrainRun
        run.finished_at = _now()
        run.selected_activity = "reflect"
        run.stop_reason = "completed" if reflect_result.get("ok") else "error"

        thought = reflect_result.get("summary", reason)
        summary = run.to_summary()
        summary["thought_summary"] = thought[:200]
        summary["reflect_result"] = {
            "ok": reflect_result.get("ok"),
            "skipped": reflect_result.get("skipped"),
            "updated_fields": reflect_result.get("updated_fields", []),
        }
        try:
            get_event_log().append_run(summary)
        except Exception as e:
            logger.warning(f"[daemon] reflect log append failed: {e}")

        self._state.set_loop_status("idle_thinking", activity="wait")
        self._state.update_life_node({
            "current_activity": "reflect",
            "next_wake_hint": {"tick_type": _next_tick(tick_type), "reason": reason},
        })

        # daily_tick 走 reflect 路径，这里补一次日沉淀触发
        self._maybe_consolidate(tick_type)

        logger.info(
            f"[tick] {tick_type} activity=reflect "
            f"ok={reflect_result.get('ok')} skipped={reflect_result.get('skipped')} "
            f"fields={reflect_result.get('updated_fields', [])} "
            f"thought={thought[:80]}"
        )
        return {
            "run_id": run.run_id,
            "tick_type": tick_type,
            "selected_activity": "reflect",
            "reason": reason,
            "cycle_count": 0,
            "stop_reason": run.stop_reason,
            "thought_summary": thought[:160],
            "reflect_result": reflect_result,
            "dry_run": False,
        }

    def _maybe_consolidate(self, tick_type: str) -> None:
        """daily_tick 时触发输出记忆沉淀（仅 dayliy，受开关控制）。"""
        if tick_type != TICK_DAILY:
            return
        try:
            from .consolidation import (
                enqueue_consolidation, is_auto_trigger_enabled, TRIGGER_DAILY_TICK,
            )
            if is_auto_trigger_enabled(TRIGGER_DAILY_TICK):
                enqueue_consolidation(TRIGGER_DAILY_TICK)
        except Exception as e:
            logger.warning(f"[daemon] daily consolidate trigger failed: {e}")

    # ── TickInput 构造 ───────────────────────────────────────
    def _build_tick_input(self, tick_type: str):
        from .contracts import TickInput
        from modules.brain.state import times
        life_state = self._state.read_life_state()
        recent_runs = get_event_log().recent_runs(limit=8, mode=BACKGROUND)
        recent_user, recent_assistant = self._recent_messages()

        # 记忆摘要：尽力取少量，失败置空（不阻塞）
        memory_items = []
        if life_state.get("open_loops"):
            try:
                from modules.brain.memory.core import search_memory
                q = (life_state["open_loops"][0].get("content", "")
                     if isinstance(life_state["open_loops"][0], dict) else "")
                if q:
                    memory_items = [{"text": m.get("text", "")[:80]}
                                    for m in search_memory(q)[:3]]
            except Exception:
                pass

        try:
            pending = self._expr._pending().get_unexpressed()
        except Exception:
            pending = []

        return TickInput(
            tick_id=f"tick_{times.now_iso().replace(':','').replace('-','')}",
            tick_type=tick_type,
            now=times.now_iso(),
            life_state=life_state,
            recent_runs=recent_runs,
            recent_user_messages=recent_user,
            recent_assistant_messages=recent_assistant,
            memory_digest={"items": memory_items},
            pending_expressions=pending,
            tool_context={"available": self._tools.available_tools()},
            budgets={},
        )

    def _recent_messages(self, limit: int = 8) -> tuple[list[dict], list[dict]]:
        try:
            from modules.brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            users, assts = [], []
            for e in entries[-limit:]:
                if e.get("user"):
                    users.append({"content": str(e["user"])[:200]})
                if e.get("assistant"):
                    assts.append({"content": str(e["assistant"])[:200]})
            return users, assts
        except Exception:
            return [], []

    def _compute_idle_seconds(self, life_state: dict) -> int:
        last = life_state.get("last_user_contact_at", "")
        if not last:
            return int(life_state.get("idle_seconds", 0) or 0) + 30
        try:
            from modules.brain.state import times
            return int(times.hours_since(last) * 3600)
        except Exception:
            return 0

    @staticmethod
    def _compute_energy(life_state: dict, idle: int) -> float:
        """空闲越久精力恢复越多（简单模型，0.2~0.9）。"""
        base = float(life_state.get("energy", 0.6) or 0.6)
        recover = min(0.3, idle / 3600.0 * 0.1)
        return max(0.2, min(0.9, base + recover))


def _is_chat_busy() -> bool:
    """用户是否正在 SSE 聊天（best-effort）。"""
    try:
        from modules.chat import ChatManager
        return bool(ChatManager.get_instance().get_status())
    except Exception:
        return False


def _next_tick(tick_type: str) -> str:
    order = [TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY]
    if tick_type in order:
        idx = order.index(tick_type)
        return order[min(idx + 1, len(order) - 1)]
    return TICK_MEDIUM


def _new_run_id(mode: str) -> str:
    from modules.brain.state import times
    import hashlib
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    prefix = "br" if mode == "reactive" else "bg"
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:4]
    return f"{prefix}_{stamp}_{suffix}"


def _now() -> str:
    from modules.brain.state import times
    return times.now_iso()
