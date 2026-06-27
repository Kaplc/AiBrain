"""LifeLoopDaemon — 常驻数字生命循环（T013）

用户无输入时维持自己的节奏。run_tick(tick_type) 是单次闭环（plan 第七节 tick 固定
读写契约）：读固定上下文 → ActivitySelector 选活动 → 通过 Activity Registry 分发
→ 表达闸门 → 更新 LifeState → 记 brain_runs.jsonl。

关键变化（T013-r2）：活动分发不再靠硬编码 if/elif，而是通过 activities/registry
的 handler_name 映射。每个活动 .md 文件定义它的 handler，daemon 在 __init__ 中注册
自己的方法作为 handler。新增活动 = 新增 .md 文件 + 注册 handler（可选）。

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
        # 注册自己的 handler 到活动注册表
        self._register_handlers()

    def _register_handlers(self) -> None:
        """将 daemon 方法注册到 activities registry。

        每个 handler 的签名统一为：
            handler(run, tick_type, reason, tick_input, ctx) -> dict

        handler_name 对应 .md 文件中的 handler_name 字段。
        """
        from .activities.registry import register_handler
        register_handler("reflect", self._run_reflect_activity)
        register_handler("self_learn", self._run_self_learn_activity)
        register_handler("review_learned", self._run_review_learned_activity)
        register_handler("wait", self._run_wait_activity)
        register_handler("daemon_cycle", self._run_daemon_cycle)
        logger.debug("[daemon] handlers registered: reflect, self_learn, review_learned, wait, daemon_cycle")

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
        """执行一次 life tick。Returns: TickOutput 摘要 dict。

        分发逻辑（T013-r2）：
          1. short_tick → 固定 wait（不调 LLM）
          2. ActivitySelector 选活动
          3. 优先走 activities.registry.run_activity()
          4. 无 handler → fallback 通用 controller 路径（保持兼容）
          5. 表达闸门评估 + 状态持久化 + 日志
        """
        cfg = get_brain_config()
        max_cycles = int(cfg.get(_TICK_MAX_CYCLES.get(tick_type, "medium_tick_max_cycles"), 0))
        timeout = float(cfg.get("background_tick_timeout_seconds", 30))

        # T005: tick 事件入脑（失败降级，不阻塞）
        try:
            from .contracts import make_tick_event
            from .orchestrator import Orchestrator
            tick_event = make_tick_event(tick_type)
            Orchestrator.get_instance().process_event(tick_event, max_depth=2)
        except Exception:
            pass

        # 1. 读固定上下文 → TickInput
        tick_input = self._build_tick_input(tick_type)
        life_state = tick_input.life_state

        # 发射 tick 开始事件
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "tick_started", {
                "tick_type": tick_type,
                "idle_seconds": life_state.get("idle_seconds", 0),
                "life_loop_status": life_state.get("life_loop_status", ""),
            })
        except Exception:
            pass

        # 短 tick：更新 idle/energy/status，不调 LLM
        if tick_type == TICK_SHORT:
            return self._run_short_tick(life_state, dry_run)

        # 2. ActivitySelector 选活动（规则式，基底核）
        from .activity_selector import get_activity_selector
        selector = get_activity_selector()
        activity, reason, confidence = selector.select(
            life_state, tick_type,
            recent_runs=tick_input.recent_runs,
            pending_expressions=tick_input.pending_expressions,
            autonomy_level=cfg.autonomy_level,
        )
        if activity_override:
            activity = activity_override
            confidence = 1.0

        # 发射活动选择事件
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "activity_selected", {
                "activity": activity,
                "reason": reason[:120],
                "confidence": round(confidence, 2),
                "tick_type": tick_type,
            })
        except Exception:
            pass

        # 2a. 自然记忆回放：长时间空闲 + 深夜/黎明 → 优先触发 memory replay
        if not dry_run and not activity_override:
            replay = _maybe_natural_replay(life_state, tick_type, activity, reason)
            if replay is not None:
                activity, reason = replay

        # 2b. 低置信时启动 Arbiter（前额叶仲裁层，FR-014-r2）
        if not dry_run and not activity_override and cfg.get("arbiter_enabled", True):
            try:
                from .arbiter import get_arbiter, needs_arbitration
                arbiter = get_arbiter()
                # 动态计算仲裁阈值（考虑当前状态）
                arbiter_threshold = cfg.get("arbiter_threshold", 0.55)
                needs_arb = needs_arbitration(confidence, float(arbiter_threshold))

                if needs_arb:
                    logger.info(
                        f"[arbiter] triggered: activity={activity} "
                        f"confidence={confidence:.2f} < threshold={arbiter_threshold}"
                    )
                    # 注入用户最近消息供情感检测
                    life_state_w_msgs = dict(life_state)
                    life_state_w_msgs["recent_user_messages"] = (
                        tick_input.recent_user_messages or []
                    )
                    arbiter_activity, arbiter_reason, arbiter_conf = arbiter.arbitrate(
                        life_state=life_state_w_msgs,
                        tick_type=tick_type,
                        recent_runs=tick_input.recent_runs,
                        fallback=(activity, reason),
                    )
                    # 只有当 Arbiter 选择了不同活动时才覆盖
                    if arbiter_activity != activity:
                        logger.info(
                            f"[arbiter] overrode {activity} -> {arbiter_activity} "
                            f"(reason: {arbiter_reason[:60]})"
                        )
                        activity = arbiter_activity
                        reason = f"[arbiter] {arbiter_reason}"
                    else:
                        logger.info(
                            f"[arbiter] confirmed {activity}"
                        )
                # 记录活动（供 novelty + 兴趣衰减）
                topic = tick_input.life_state.get("current_focus", "")
                arbiter.record_activity(tick_type, activity, topic=topic)
            except Exception as e:
                logger.warning(f"[arbiter] failed (safe fallback): {e}")
                # 失败降级：继续使用规则式结果

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
            tool_context=tick_input.tool_context,
        )

        # 4. 状态切到 active_reflecting
        if not dry_run:
            self._state.set_loop_status("active_reflecting", activity=activity,
                                        focus=life_state.get("current_focus", ""))

        logger.info(
            f"[tick] {tick_type} activity={activity} cycles={max_cycles} "
            f"reason={reason[:60]}"
        )

        # 5. 通过 Activity Registry 分发（取代硬编码 if/elif）
        # 记录 result_meta 供后续通用流程使用
        handler_result = self._dispatch_activity(
            activity, run, tick_type, reason, tick_input, ctx,
            max_cycles=max_cycles, timeout=timeout, cfg=cfg, dry_run=dry_run,
        )

        # 5a. 通用后处理：learning_hints 沉淀
        self._sink_learning_hints(handler_result, dry_run)

        # 5b. 表达闸门（需表达且有 pending 的活动才评估）
        gate_out = self._run_expression_gate(
            handler_result, tick_type, tick_input, dry_run,
        )

        # 发射闸门事件
        if gate_out.get("gate"):
            try:
                from core.event_bus import get_event_bus
                get_event_bus().emit("brain", "gate", {
                    "activity": activity,
                    "gate_action": gate_out["gate"].get("action", ""),
                    "allowed": gate_out["gate"].get("allowed", False),
                    "sent": gate_out.get("sent", False),
                })
            except Exception:
                pass

        # 5c. 更新 life 状态 + 写日志
        tick_summary = self._finalize_tick(
            handler_result, tick_type, activity, reason, dry_run,
            run_id=run.run_id,
        )
        tick_summary["gate"] = gate_out.get("gate", {})
        tick_summary["sent"] = gate_out.get("sent", False)

        # 发射 tick 完成事件
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "tick_completed", {
                "tick_type": tick_type,
                "activity": activity,
                "stop_reason": tick_summary.get("stop_reason", ""),
                "actions": tick_summary.get("actions", []),
                "cycle_count": tick_summary.get("cycle_count", 0),
            })
        except Exception:
            pass

        return tick_summary

    # ── 活动分发 ──────────────────────────────────────────────

    def _dispatch_activity(self, activity: str, run: BrainRun,
                           tick_type: str, reason: str, tick_input,
                           ctx: BrainRunContext, *, max_cycles: int,
                           timeout: float, cfg, dry_run: bool) -> dict:
        """通过 registry 分发活动，返回统一结果 dict。

        Returns 统一 schema:
            ok: bool
            stop_reason: str
            thought_summary: str
            actions: list[str]
            cycle_count: int
            activity_result: dict      # 活动专有数据
            learning_hints: list[str]
            needs_gate: bool           # 是否应评估表达闸门
        """
        from .activities.registry import get_activity, run_activity

        act_def = get_activity(activity)
        # 有 handler 就走 registry 分发
        if act_def is not None and act_def.handler is not None:
            result = run_activity(
                activity,
                run=run, tick_type=tick_type, reason=reason,
                tick_input=tick_input, ctx=ctx,
                max_cycles=max_cycles, timeout=timeout, cfg=cfg,
                dry_run=dry_run,
            )
            if isinstance(result, dict):
                return result

        # 无 handler 或 handler 返回非 dict → fallback 通用 controller 路径
        return self._run_daemon_cycle(
            run=run, tick_type=tick_type, reason=reason,
            tick_input=tick_input, ctx=ctx,
            max_cycles=max_cycles, timeout=timeout, cfg=cfg,
            dry_run=dry_run,
        )

    # ── activity handlers ─────────────────────────────────────

    def _run_wait_activity(self, run, tick_type, reason, tick_input, ctx, *,
                           dry_run=False, **kwargs) -> dict:
        """wait 活动：不做任何 LLM 调用。"""
        run.finished_at = _now()
        run.stop_reason = "sleep"
        run.selected_activity = "wait"
        # wait 的 life_state 更新由 _finalize_tick 统一处理
        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "activity:wait", {"reason": reason})
        except Exception:
            pass
        return {
            "ok": True,
            "stop_reason": "sleep",
            "thought_summary": reason,
            "actions": [],
            "cycle_count": 0,
            "activity_result": {},
            "learning_hints": [],
            "needs_gate": False,
        }

    def _run_reflect_activity(self, run, tick_type, reason, tick_input, ctx, *,
                              dry_run=False, **kwargs) -> dict:
        """reflect 活动：直接调反思核心，不走 LLM BrainJudge。"""
        if dry_run:
            return {"ok": True, "stop_reason": "sleep",
                    "thought_summary": "dry_run", "cycle_count": 0,
                    "activity_result": {}, "learning_hints": [], "needs_gate": False}

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

        run.finished_at = _now()
        run.selected_activity = "reflect"
        run.stop_reason = "completed" if reflect_result.get("ok") else "error"

        thought = reflect_result.get("summary", reason)
        self._maybe_consolidate(tick_type)

        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "activity:reflect", {
                "ok": reflect_result.get("ok"),
                "skipped": reflect_result.get("skipped"),
                "summary": thought[:120],
            })
        except Exception:
            pass

        return {
            "ok": reflect_result.get("ok", False),
            "stop_reason": run.stop_reason,
            "thought_summary": thought[:200],
            "actions": ["reflect"],
            "cycle_count": 0,
            "activity_result": {
                "reflect_result": {
                    "ok": reflect_result.get("ok"),
                    "skipped": reflect_result.get("skipped"),
                    "updated_fields": reflect_result.get("updated_fields", []),
                    "summary": thought[:200],
                },
            },
            "learning_hints": [],
            "needs_gate": True,
        }

    def _run_self_learn_activity(self, run, tick_type, reason, tick_input, ctx, *,
                                 dry_run=False, **kwargs) -> dict:
        """self_learn 活动：自主编排学习流程，不走 LLM controller。"""
        if dry_run:
            return {"ok": True, "stop_reason": "sleep",
                    "thought_summary": "dry_run", "cycle_count": 0,
                    "activity_result": {}, "learning_hints": [], "needs_gate": False}

        learn_result = {"ok": False, "skipped": True, "reason": "not_executed"}
        try:
            from main_brain.self_learn import run_self_learn
            learn_result = run_self_learn(tick_input, dry_run=False)
        except Exception as e:
            logger.warning(f"[daemon] self_learn activity failed: {e}")
            learn_result = {"ok": False, "skipped": True, "reason": str(e)}

        run.finished_at = _now()
        run.selected_activity = "self_learn"
        run.stop_reason = "completed" if learn_result.get("ok") else "skipped"

        thought = learn_result.get("topic", reason) or reason

        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "activity:self_learn", {
                "ok": learn_result.get("ok"),
                "skipped": learn_result.get("skipped"),
                "topic": learn_result.get("topic", ""),
                "source": learn_result.get("source", ""),
            })
        except Exception:
            pass

        return {
            "ok": learn_result.get("ok", False),
            "stop_reason": run.stop_reason,
            "thought_summary": thought[:200],
            "actions": ["self_learn"],
            "cycle_count": 0,
            "activity_result": {
                "self_learn_result": {
                    "ok": learn_result.get("ok"),
                    "skipped": learn_result.get("skipped"),
                    "topic": learn_result.get("topic", ""),
                    "source": learn_result.get("source", ""),
                },
            },
            "learning_hints": [],
            "needs_gate": False,
        }

    def _run_review_learned_activity(self, run, tick_type, reason, tick_input, ctx, *,
                                     dry_run=False, **kwargs) -> dict:
        """review_learned 活动：回顾已学知识，刷新关注度。不走 LLM controller。"""
        if dry_run:
            return {"ok": True, "stop_reason": "sleep",
                    "thought_summary": "dry_run", "cycle_count": 0,
                    "activity_result": {}, "learning_hints": [], "needs_gate": False}

        review_result = {"ok": False, "skipped": True, "reason": "not_executed"}
        try:
            from main_brain.self_learn.review import run_review
            review_result = run_review(tick_input, dry_run=False)
        except Exception as e:
            logger.warning(f"[daemon] review_learned activity failed: {e}")
            review_result = {"ok": False, "skipped": True, "reason": str(e)}

        run.finished_at = _now()
        run.selected_activity = "review_learned"
        run.stop_reason = "completed" if review_result.get("ok") else "skipped"

        thought = review_result.get("topic", reason) or reason

        try:
            from core.event_bus import get_event_bus
            get_event_bus().emit("brain", "activity:review_learned", {
                "ok": review_result.get("ok"),
                "skipped": review_result.get("skipped"),
                "topic": review_result.get("topic", ""),
            })
        except Exception:
            pass

        return {
            "ok": review_result.get("ok", False),
            "stop_reason": run.stop_reason,
            "thought_summary": thought[:200],
            "actions": ["review_learned"],
            "cycle_count": 0,
            "activity_result": {
                "review_result": {
                    "ok": review_result.get("ok"),
                    "skipped": review_result.get("skipped"),
                    "topic": review_result.get("topic", ""),
                    "memory_id": review_result.get("memory_id", ""),
                },
            },
            "learning_hints": [],
            "needs_gate": False,
        }

    def _run_daemon_cycle(self, run, tick_type, reason, tick_input, ctx, *,
                          max_cycles=3, timeout=30.0, cfg=None, dry_run=False,
                          **kwargs) -> dict:
        """通用 controller 路径：所有走 LLM judge → adapter 循环的活动。

        对应 frontmatter handler_name=daemon_cycle 的活动：
          advance_open_loop, prepare_expression, organize_memory,
          maintain_goal, proactive_contact, use_tool
        """
        # 注入程序记忆匹配（不阻塞主流程）
        try:
            from .procedural_memory.policy import enrich_tick_context_with_procedures
            ctx_data = ctx.__dict__
            ctx_data["mode"] = run.mode
            ctx_data["actions"] = [c.action for c in run.cycles]
            enrich_tick_context_with_procedures(ctx_data, dry_run=dry_run)
        except Exception:
            pass

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

        actions_summary = [c.action for c in run.cycles]
        thought = run.cycles[-1].thought_summary if run.cycles else reason

        # proactive_contact / prepare_expression 需要表达闸门评估
        needs_gate = run.selected_activity in ("proactive_contact", "prepare_expression")

        logger.info(
            f"[tick] done {tick_type} actions={actions_summary} "
            f"stop={stop_reason} cycles={len(run.cycles)} "
            f"thought={thought}"
        )

        return {
            "ok": stop_reason not in ("error",),
            "stop_reason": stop_reason,
            "thought_summary": thought[:200],
            "actions": actions_summary,
            "cycle_count": len(run.cycles),
            "activity_result": {},
            "learning_hints": list(run.learning_hints),
            "needs_gate": needs_gate,
        }

    # ── 通用后处理 ────────────────────────────────────────────

    def _sink_learning_hints(self, handler_result: dict, dry_run: bool) -> None:
        """沉淀本轮 learning_hints（后台学习，FR-010）。"""
        hints = handler_result.get("learning_hints") or []
        if not dry_run and hints:
            try:
                from .adapters.learning import get_learning_adapter
                get_learning_adapter().sink_hints(
                    hints, thought=handler_result.get("thought_summary", ""),
                    focus="", source="life_tick")
            except Exception as e:
                logger.warning(f"[daemon] sink learning_hints failed: {e}")

    def _run_expression_gate(self, handler_result: dict, tick_type: str,
                             tick_input, dry_run: bool) -> dict:
        """评估表达闸门（需表达且有 pending 的活动才评估）。"""
        gate_out = {}
        if dry_run:
            return gate_out
        if not handler_result.get("needs_gate", False):
            return gate_out
        current_pending = self._expr._pending().get_unexpressed()
        if not current_pending:
            return gate_out
        try:
            gate_out = self._expr.evaluate_and_send(
                self._state.read_life_state(),
                chat_busy=_is_chat_busy(),
                recent_messages=tick_input.recent_assistant_messages,
            )
        except Exception as e:
            logger.warning(f"[daemon] expression eval failed: {e}")
        return gate_out

    def _finalize_tick(self, handler_result: dict, tick_type: str,
                       activity: str, reason: str, dry_run: bool,
                       *, run_id: str = "") -> dict:
        """更新 life 状态 + 写日志 + 构建最终返回 dict。

        Args:
            run_id: 来自 BrainRun.run_id，用于 run 日志追踪
        """
        thought = handler_result.get("thought_summary", reason)
        cycle_count = handler_result.get("cycle_count", 0)
        stop_reason = handler_result.get("stop_reason", "sleep")

        # 写 brain_runs.jsonl
        if not dry_run:
            try:
                summary = {
                    "run_id": run_id,
                    "mode": BACKGROUND,
                    "trigger": {"tick_type": tick_type},
                    "started_at": _now(),
                    "finished_at": _now(),
                    "cycle_count": cycle_count,
                    "selected_activity": activity,
                    "actions": handler_result.get("actions", []),
                    "stop_reason": stop_reason,
                    "last_error": "",
                    "thought_summary": thought[:200],
                }
                if handler_result.get("activity_result"):
                    summary.update(handler_result["activity_result"])
                get_event_log().append_run(summary)
            except Exception as e:
                logger.warning(f"[daemon] log append failed: {e}")

        # 更新 LifeState
        if not dry_run:
            self._state.set_loop_status("idle_thinking", activity="wait")
            self._state.update_life_node({
                "current_activity": activity,
                "next_wake_hint": {"tick_type": _next_tick(tick_type), "reason": reason},
            })

        return {
            "run_id": run_id,
            "tick_type": tick_type,
            "selected_activity": activity,
            "reason": reason,
            "cycle_count": cycle_count,
            "actions": handler_result.get("actions", []),
            "stop_reason": stop_reason,
            "thought_summary": thought[:160],
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
        from main_brain.state import times
        life_state = self._state.read_life_state()
        recent_runs = get_event_log().recent_runs(limit=8, mode=BACKGROUND)
        recent_user, recent_assistant = self._recent_messages()

        # 记忆摘要：尽力取少量，失败置空（不阻塞）
        memory_items = []
        if life_state.get("open_loops"):
            try:
                from main_brain.memory.core import search_memory
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
            from main_brain.memory.workmemory import get_work_memory
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
            from main_brain.state import times
            return int(times.hours_since(last) * 3600)
        except Exception:
            return 0

    @staticmethod
    def _compute_energy(life_state: dict, idle: int) -> float:
        """空闲越久精力恢复越多（简单模型，0.2~0.9）。"""
        base = float(life_state.get("energy", 0.6) or 0.6)
        recover = min(0.3, idle / 3600.0 * 0.1)
        return max(0.2, min(0.9, base + recover))


def _maybe_natural_replay(life_state: dict, tick_type: str,
                          activity: str, reason: str) -> tuple[str, str] | None:
    """自然记忆回放：长时间空闲 + 深夜/黎明时优先触发记忆整理。

    大脑在睡眠/深度休息时会回放白天的经历。模拟这个行为：
    空闲 > 2h 且此时是深夜或黎明 → 尝试把当前活动改为 organize_memory，
    但只在当前活动是 wait/reflect 等低价值活动时才覆盖。

    Returns:
        (activity, reason) 或 None（不覆盖）
    """
    try:
        idle = float(life_state.get("idle_seconds", 0) or 0)
        if idle < 7200:
            return None  # 空闲不足 2h
        # 昼夜节律检测
        from .arbiter import get_circadian_phase
        phase = get_circadian_phase()
        if phase not in ("night", "dawn"):
            return None  # 不是深夜/黎明
        # 只在当前活动是低价值时才覆盖
        if activity in ("wait", "reflect", ""):
            logger.info(
                f"[daemon] natural replay triggered: idle={idle:.0f}s "
                f"phase={phase} activity={activity} -> organize_memory"
            )
            return ("organize_memory",
                    f"自然记忆回放：空闲 {idle:.0f}s + {phase}，整理记忆")
    except Exception:
        pass
    return None


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
    from main_brain.state import times
    import hashlib
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")
    prefix = "br" if mode == "reactive" else "bg"
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:4]
    return f"{prefix}_{stamp}_{suffix}"


def _now() -> str:
    from main_brain.state import times
    return times.now_iso()
