"""BrainCycleRunner — 通用循环执行器（T004）

reactive session 与 background tick 共用的 cycle runner：
  judge → 路由 next_action 到 adapter → 记录 cycle → 检查停止条件 → 循环。

停止条件（plan FR-012 安全停止）：max_cycles / timeout / budget / abort /
sleep(后台) / final_reply(reactive ready)。

adapter 通过 action_handlers 注入，runner 本身不 import 具体 adapter，保持解耦
（plan 第六节决策：LLM 只判断，副作用由 Python adapter 执行）。

handler 约定：
    handler(decision, ctx, dry_run) -> dict
    返回 {"result_summary", "memory_context"?, "tool_results"?, "state_delta"?,
          "pending_created"?, "notify_candidate"?}
"""
from __future__ import annotations

import logging
import time as _t
from typing import Callable

from .contracts import (
    ACTIONS, REACTIVE, BACKGROUND, BrainCycle, BrainRunContext, BrainJudgeDecision,
)

logger = logging.getLogger("main_brain.controller")

ActionHandler = Callable[[BrainJudgeDecision, BrainRunContext, bool], dict]

# 终止动作：不需要 adapter，直接结束循环
_TERMINAL_ACTIONS = {"final_reply", "sleep", "abort"}


class BrainCycleRunner:
    """通用 cycle runner。judge 与 action_handlers 由调用方注入。"""

    def __init__(self, judge, action_handlers: dict[str, ActionHandler] | None = None):
        self._judge = judge
        self._handlers: dict[str, ActionHandler] = dict(action_handlers or {})

    def register(self, action: str, handler: ActionHandler) -> None:
        self._handlers[action] = handler

    # ── 主循环 ───────────────────────────────────────────────
    def run(
        self,
        ctx: BrainRunContext,
        *,
        max_cycles: int = 3,
        timeout_seconds: float = 60.0,
        budgets: dict | None = None,
        dry_run: bool = False,
        mock_judge=None,
    ) -> str:
        """执行循环，返回 stop_reason。结果写进 ctx.run。

        Args:
            max_cycles: 最多几轮 judge。
            timeout_seconds: 总超时（软超时，轮间检查）。
            budgets: 预算 {max_tools, max_tokens}（可选）。
            dry_run: True 时跳过真实 LLM 和 adapter 副作用，仅记录决策路径。
            mock_judge: dry_run 时使用的假 judge。None 时自动用默认 mock
                      （reactive→final_reply，background→sleep）。
        """
        budgets = budgets or {}
        max_cycles = max(0, int(max_cycles))
        t0 = _t.perf_counter()
        stop_reason = "max_cycles"

        # dry_run 时使用 mock judge，不碰真实 LLM
        judge = self._judge
        if dry_run:
            if mock_judge is not None:
                judge = mock_judge
            else:
                judge = self._default_mock_judge(ctx.run.mode)

        for i in range(1, max_cycles + 1):
            # 软超时检查（轮间）
            if (_t.perf_counter() - t0) > timeout_seconds:
                stop_reason = "timeout"
                logger.info(f"[runner] timeout at cycle {i} (run={ctx.run.run_id})")
                break

            # 外部打断：用户开始聊天时提前退出循环（中断响应）
            # 至少完成 1 个完整 cycle 后才允许打断，防止后台任务被饿死
            if i > 1 and not dry_run and ctx.run.mode == BACKGROUND:
                try:
                    if _is_chat_busy():
                        stop_reason = "preempted"
                        logger.info(
                            f"[runner] preempted at cycle {i} — user chatting "
                            f"(run={ctx.run.run_id})"
                        )
                        break
                except Exception:
                    pass

            # 预算检查
            if _budget_exhausted(ctx, budgets):
                stop_reason = "timeout"
                logger.info(f"[runner] budget exhausted at cycle {i}")
                break

            view = ctx.to_judge_view()
            jr = judge.decide(
                view, mode=ctx.run.mode, activity=ctx.selected_activity
            )
            decision = jr.decision

            logger.info(
                f"[cycle {i}/{max_cycles}] action={decision.next_action} "
                f"focus={decision.focus[:24] or '-'} "
                f"conf={decision.confidence:.2f} "
                f"thought={decision.thought_summary}"
            )

            cycle = BrainCycle(
                cycle_index=i,
                thought_summary=decision.thought_summary,
                focus=decision.focus,
                action=decision.next_action,
                action_args=decision.action_args,
                confidence=decision.confidence,
                latency_ms=jr.latency_ms,
            )
            if jr.error:
                cycle.error = jr.error

            # 终止动作：记录即结束
            if decision.next_action in _TERMINAL_ACTIONS:
                self._apply_terminal(decision, ctx, cycle, dry_run)
                ctx.run.cycles.append(cycle)
                self._emit_cycle(cycle, ctx)
                stop_reason = self._terminal_stop_reason(decision.next_action)
                logger.info(
                    f"[runner] terminal {decision.next_action} at cycle {i} "
                    f"(run={ctx.run.run_id})"
                )
                break

            # 非法/未知动作：记 error，结束
            if decision.next_action not in ACTIONS or decision.next_action not in self._handlers:
                cycle.error = cycle.error or f"no handler for {decision.next_action!r}"
                ctx.add_error(cycle.error)
                ctx.run.cycles.append(cycle)
                stop_reason = "error"
                logger.warning(f"[runner] {cycle.error} (run={ctx.run.run_id})")
                break

            # 执行 adapter
            try:
                if dry_run:
                    result = {
                        "result_summary": f"[dry_run] would {decision.next_action}: "
                                          f"{str(decision.action_args)[:80]}"
                    }
                else:
                    handler = self._handlers[decision.next_action]
                    result = handler(decision, ctx, dry_run) or {}
                cycle.result_summary = str(result.get("result_summary", ""))[:300]
                self._merge_result(ctx, cycle, result)
                if result.get("notify_candidate"):
                    cycle.notify_candidate = result["notify_candidate"]
            except Exception as e:
                logger.warning(f"[runner] handler {decision.next_action} error: {e}")
                cycle.error = str(e)
                ctx.add_error(str(e))
                # 单步失败降级：继续下一轮而非整体崩（plan 非功能 #4）

            ctx.run.cycles.append(cycle)
            self._emit_cycle(cycle, ctx)

            # 收集 learning_hints（caller 在 run 结束后统一沉淀）
            if decision.learning_hints:
                ctx.run.learning_hints.extend(decision.learning_hints)

            # 非 update_state 动作附带 state_updates 时统一落盘；
            # update_state 动作已由其 handler 落盘，避免重复应用。
            if (decision.state_updates and not dry_run
                    and decision.next_action != "update_state"):
                _apply_state_updates(decision, ctx)

        else:
            # for 循环正常跑满（未 break）
            stop_reason = "max_cycles"

        # ── Auto-recall：reactive 模式没出 final_reply 且没搜过记忆时自动补一轮 ──
        if (stop_reason != "ready"
                and ctx.run.mode == REACTIVE
                and not any(c.action == "recall_memory" for c in ctx.run.cycles)):
            try:
                user_msg = ctx.trigger.get("user_message", "")
                if user_msg:
                    from main_brain.memory.core import search_memory
                    memories = search_memory(user_msg)[:3]
                    if memories:
                        auto_recall_ctx = [
                            {"text": m.get("text", "")[:160],
                             "score": m.get("score", 0.0)}
                            for m in memories if m.get("text")
                        ]
                        ctx.memory_context = auto_recall_ctx
                        ctx.run.memory_context = list(auto_recall_ctx)
                        # 用更新后的 memory_context 再跑一轮 judge
                        i = len(ctx.run.cycles) + 1
                        view = ctx.to_judge_view()
                        jr = judge.decide(view, mode=ctx.run.mode,
                                          activity=ctx.selected_activity)
                        decision = jr.decision
                        cycle = BrainCycle(
                            cycle_index=i,
                            thought_summary=decision.thought_summary,
                            focus=decision.focus,
                            action=decision.next_action,
                            action_args=decision.action_args,
                            confidence=decision.confidence,
                            latency_ms=jr.latency_ms,
                        )
                        if jr.error:
                            cycle.error = jr.error
                        if decision.next_action == "final_reply":
                            self._apply_terminal(decision, ctx, cycle, dry_run)
                            ctx.run.cycles.append(cycle)
                            self._emit_cycle(cycle, ctx)
                            stop_reason = "ready"
                        elif decision.next_action not in ACTIONS:
                            cycle.error = f"auto-recall judge gave invalid action: {decision.next_action}"
                            ctx.add_error(cycle.error)
                        else:
                            ctx.run.cycles.append(cycle)
                            self._emit_cycle(cycle, ctx)
                        logger.info(
                            f"[runner] auto-recall at cycle {i} "
                            f"action={decision.next_action} stop={stop_reason}"
                        )
            except Exception as e:
                logger.warning(f"[runner] auto-recall failed (non-fatal): {e}")

        ctx.run.stop_reason = stop_reason
        return stop_reason

    # ── 终止动作处理 ─────────────────────────────────────────
    def _apply_terminal(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                        cycle: BrainCycle, dry_run: bool) -> None:
        if decision.next_action == "final_reply":
            # reply handler 负责落 final_strategy；dry_run 时只记录
            handler = self._handlers.get("final_reply")
            if handler and not dry_run:
                try:
                    result = handler(decision, ctx, dry_run) or {}
                    cycle.result_summary = str(result.get("result_summary", ""))[:200]
                    if result.get("state_delta"):
                        ctx.run.state_deltas.append(result["state_delta"])
                except Exception as e:
                    cycle.error = str(e)
            else:
                ctx.run.final_strategy = decision.reply_strategy
                cycle.reply_ready = True
            cycle.reply_ready = True
        # sleep / abort 不做事

    @staticmethod
    def _terminal_stop_reason(action: str) -> str:
        if action == "final_reply":
            return "ready"
        if action == "sleep":
            return "sleep"
        return "error"

    @staticmethod
    def _emit_cycle(cycle: "BrainCycle", ctx: BrainRunContext) -> None:
        """通过 EventBus 发射当前 cycle 的动作事件。"""
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "cycle", {
                "action": cycle.action,
                "focus": cycle.focus,
                "thought_summary": cycle.thought_summary[:80],
                "confidence": cycle.confidence,
                "run_id": ctx.run.run_id,
                "mode": ctx.run.mode,
            })
        except Exception:
            pass

    @staticmethod
    def _default_mock_judge(mode: str):
        """dry_run 默认假 judge（内联，不碰真实 LLM）。"""
        from .contracts import BrainJudgeDecision, REACTIVE as _REACTIVE
        from .judge import JudgeResult
        _mode = mode
        class _Mock:
            def decide(self, view, mode="", activity="", *, mock_response=None):
                if _mode == _REACTIVE:
                    d = BrainJudgeDecision(next_action="final_reply", thought_summary="dry_run mock", confidence=1.0)
                else:
                    d = BrainJudgeDecision(next_action="sleep", thought_summary="dry_run mock", confidence=1.0)
                d.mode = mode
                return JudgeResult(decision=d, schema_valid=True, latency_ms=0.1)
        return _Mock()

    # ── 结果合并 ─────────────────────────────────────────────
    @staticmethod
    def _merge_result(ctx: BrainRunContext, cycle: BrainCycle, result: dict) -> None:
        if result.get("memory_context"):
            ctx.memory_context.extend(result["memory_context"])
            ctx.run.memory_context.extend(result["memory_context"])
        if result.get("tool_results"):
            ctx.tool_results.extend(result["tool_results"])
            ctx.run.tool_results.extend(result["tool_results"])
        if result.get("state_delta"):
            ctx.run.state_deltas.append(result["state_delta"])
        if result.get("pending_created"):
            ctx.run.pending_created.extend(result["pending_created"])


def _apply_state_updates(decision: BrainJudgeDecision, ctx: BrainRunContext) -> None:
    """把 judge 的 state_updates 转发给 state adapter（若注册）。

    state adapter 通过 ctx.config["_state_adapter"] 指向，避免循环依赖。
    只记录 delta 摘要，真正落盘由 state adapter 在 handler 内完成；这里兜底
    处理 judge 直接给 state_updates 但下一动作不是 update_state 的少见情况。
    """
    adapter = ctx.config.get("_state_adapter")
    if adapter is None:
        return
    try:
        delta = adapter.apply_state_updates(decision.state_updates)
        if delta:
            ctx.run.state_deltas.append({"source": "judge_state_updates", "delta": delta})
    except Exception as e:
        logger.warning(f"[runner] apply_state_updates failed: {e}")


def _budget_exhausted(ctx: BrainRunContext, budgets: dict) -> bool:
    if not budgets:
        return False
    max_tools = budgets.get("max_tools")
    if max_tools is not None and len(ctx.tool_results) >= int(max_tools):
        return True
    return False


def _is_chat_busy() -> bool:
    """用户是否正在 SSE 聊天（中断响应用）。"""
    try:
        from modules.chat import ChatManager
        return bool(ChatManager.get_instance().get_status())
    except Exception:
        return False


# ── 单例 ─────────────────────────────────────────────────────
_runner: BrainCycleRunner | None = None


def get_cycle_runner() -> BrainCycleRunner:
    """获取装配好所有 adapter 的 runner 单例。

    延迟 import adapter，避免模块加载顺序问题。
    """
    global _runner
    if _runner is None:
        from .judge import get_brain_judge
        from .adapters import build_action_handlers
        _runner = BrainCycleRunner(get_brain_judge(), build_action_handlers())
    return _runner
