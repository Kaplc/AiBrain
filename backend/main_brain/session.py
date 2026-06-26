"""Reactive BrainSession（T005 / FR-001）

用户消息触发：在一次对话内运行多轮内部思考，再交回现有 chat 链路生成可见回复。
不自己发 SSE——它只跑内部循环、更新状态、记录 run，然后把 reply_strategy 交回
chat_routes（plan 流程图：RS → ... → C: send(brain_context)）。

失败必须降级：任何异常都不影响现有 chat SSE（plan 非功能 #4 / FR-013）。
"""
from __future__ import annotations

import logging

from .config import get_brain_config
from .contracts import (
    REACTIVE, BrainRun, BrainRunContext, BACKGROUND,
)
from .logging.event_log import get_event_log

logger = logging.getLogger("main_brain.session")


def _new_run_id(mode: str) -> str:
    from main_brain.state import times
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    prefix = "br" if mode == REACTIVE else "bg"
    # 加 4 位后缀区分同一秒多次
    import hashlib
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:4]
    return f"{prefix}_{stamp}_{suffix}"


class BrainSession:
    """Reactive BrainSession 单例。"""

    def __init__(self):
        from .adapters.state import get_state_adapter
        self._state = get_state_adapter()
        from .adapters.tools import get_tool_adapter
        self._tools = get_tool_adapter()

    def run_reactive(
        self,
        user_msg: str,
        *,
        max_cycles: int | None = None,
        timeout_seconds: float | None = None,
        dry_run: bool = False,
    ) -> dict:
        """运行一次 reactive session。

        Returns: {
            run_id, stop_reason, cycle_count, reply_strategy,
            actions, errors, ok
        }
        """
        cfg = get_brain_config()
        max_cycles = max_cycles if max_cycles is not None else int(cfg.get("brain_session_max_cycles", 3))
        timeout = timeout_seconds if timeout_seconds is not None else float(cfg.get("brain_session_timeout_seconds", 60))

        run = BrainRun(
            run_id=_new_run_id(REACTIVE),
            mode=REACTIVE,
            started_at=_now(),
        )

        # 读取 LifeState + 标记用户接触 + 状态切到 chatting
        try:
            life_state = self._state.read_life_state()
            if not dry_run:
                self._state.mark_user_contact()
                self._state.set_loop_status("chatting", activity="reflect", focus=user_msg[:40])
        except Exception as e:
            logger.warning(f"[session] read life_state failed: {e}")
            life_state = {}

        ctx = BrainRunContext(
            run=run,
            life_state=life_state,
            trigger={"user_message": user_msg[:500]},
            config={"_state_adapter": self._state},
            budgets={"max_tools": int(cfg.get("brain_session_max_cycles", 3))},
            tool_context={"available": self._tools.available_tools()},
        )

        # 附加最近对话上下文，让 judge 的 recall_memory query 更准确
        try:
            from main_brain.memory.workmemory import get_work_memory
            entries = get_work_memory().output_mem_read()
            recent = []
            for e in entries[-6:]:
                if e.get("user"):
                    recent.append(f"用户: {e['user'][:200]}")
                if e.get("assistant"):
                    recent.append(f"助手: {e['assistant'][:200]}")
            if recent:
                ctx.trigger["recent_conversation"] = "\n".join(recent)
        except Exception:
            pass

        # inject procedural memory matches (non-blocking)
        try:
            from .procedural_memory.policy import enrich_tick_context_with_procedures
            ctx_data = ctx.__dict__
            ctx_data["mode"] = run.mode
            ctx_data["actions"] = [c.action for c in run.cycles]
            enrich_tick_context_with_procedures(ctx_data, dry_run=dry_run)
        except Exception:
            pass

        ok = True
        try:
            from .controller import get_cycle_runner
            runner = get_cycle_runner()
            stop_reason = runner.run(
                ctx, max_cycles=max_cycles, timeout_seconds=timeout,
                budgets=ctx.budgets, dry_run=dry_run,
            )
            run.finished_at = _now()
        except Exception as e:
            logger.exception(f"[session] reactive run failed: {e}")
            stop_reason = "fallback"
            run.stop_reason = stop_reason
            ok = False

        # reactive 跑满或异常但没 final_reply → 兜底 ready，让旧链路回复
        if not any(c.action == "final_reply" for c in run.cycles):
            if stop_reason != "ready":
                stop_reason = "fallback"
                run.stop_reason = stop_reason

        # 记日志 + 更新状态
        # 沉淀本轮 learning_hints（后台学习，不阻塞回复）
        if not dry_run and run.learning_hints:
            try:
                from .adapters.learning import get_learning_adapter
                thought = run.cycles[-1].thought_summary if run.cycles else ""
                get_learning_adapter().sink_hints(
                    run.learning_hints, thought=thought,
                    focus=user_msg[:40], source="reactive_reply")
            except Exception as e:
                logger.warning(f"[session] sink learning_hints failed: {e}")
        summary = run.to_summary()
        try:
            get_event_log().append_run(summary, full=run.to_full())
        except Exception as e:
            logger.warning(f"[session] log append failed: {e}")
        if not dry_run:
            try:
                self._state.set_loop_status("idle_thinking", activity="wait")
            except Exception:
                pass

        reply_strategy = run.final_strategy or {}
        return {
            "ok": ok,
            "run_id": run.run_id,
            "stop_reason": stop_reason,
            "cycle_count": len(run.cycles),
            "reply_strategy": reply_strategy,
            "actions": summary.get("actions", []),
            "errors": ctx.errors,
            "thoughts": [
                {"focus": c.focus, "summary": c.thought_summary, "action": c.action}
                for c in run.cycles if c.thought_summary
            ][:4],
        }


def _now() -> str:
    from main_brain.state import times
    return times.now_iso()
