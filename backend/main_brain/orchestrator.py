"""事件编排器（T002 / FR-002）

统一中枢入口：接收 BrainEvent → 感知 → 注意 → 记忆 → 状态 → 决策 → 动作。
支持预算控制、深度限制、降级回退。

事件处理流程:
  process_event(event)
    ├─ 1. NewBrainCycleContext(event)       — 包装事件上下文
    ├─ 2. Perception / Salience              — 感知与显著性评估
    ├─ 3. Attention / Focus                  — 注意力分配
    ├─ 4. Memory Adapter                     — 记忆召回
    ├─ 5. State Adapter                      — 状态更新
    ├─ 6. BrainJudge / Rule Selector         — 决策
    ├─ 7. Action dispatch                    — 动作执行
    └─ 8. Feedback → 回灌或结束
"""
from __future__ import annotations

import logging
import threading
import time as _t
from typing import Any

from .config import EVENT_ORCHESTRATOR_ENABLED, get_brain_config
from .contracts import (
    BrainEvent, BrainCycleContext,
    EVENT_SOURCE_CHAT, EVENT_SOURCE_TOOL, EVENT_SOURCE_TICK,
    EVENT_TYPE_USER_MESSAGE, EVENT_TYPE_TOOL_RESULT,
)
from .router import route, register_default_handlers

logger = logging.getLogger("main_brain.orchestrator")

# ── 默认限制参数 ─────────────────────────────────────────────
_DEFAULT_MAX_DEPTH = 5        # 单事件最大处理深度
_DEFAULT_TIMEOUT = 30.0       # 单事件超时（秒）
_DEFAULT_BUDGET = 5           # 单 trace 最大循环次数


class Orchestrator:
    """事件编排器单例 — 所有事件的中枢入口。

    线程安全：process_event 可并发调用，每个事件独立处理。
    """

    _instance: Orchestrator | None = None
    _lock = threading.Lock()

    def __init__(self):
        self._initialized = False
        self._trace_depth: dict[str, int] = {}  # trace_id -> depth
        self._trace_budget: dict[str, int] = {}  # trace_id -> used_cycles

    @classmethod
    def get_instance(cls) -> "Orchestrator":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 生命周期 ─────────────────────────────────────────────
    def initialize(self) -> None:
        """初始化：注册默认处理器 + 事件适配器。由 app 启动时调用一次。"""
        if self._initialized:
            return
        register_default_handlers()
        try:
            from .event_adapters import register_event_adapters
            register_event_adapters()
        except Exception as e:
            logger.warning(f"[orchestrator] event_adapters registration failed: {e}")
        self._initialized = True
        logger.info("[orchestrator] initialized with default handlers + event_adapters")

    # ── 主入口 ───────────────────────────────────────────────
    def process_event(
        self,
        event: BrainEvent,
        *,
        max_depth: int | None = None,
        timeout: float | None = None,
        dry_run: bool = False,
    ) -> BrainCycleContext:
        """处理一个事件，返回完整周期上下文。

        支持深度/预算/超时三重保护。失败降级，绝不崩溃。

        Args:
            event: 待处理事件
            max_depth: 同一 trace 最大处理深度（默认 5）
            timeout: 该事件超时（秒，默认 30）
            dry_run: 仅记录不执行副作用

        Returns:
            BrainCycleContext: 完整处理上下文（含所有中间结果）
        """
        cfg = get_brain_config()
        max_depth = max_depth or _DEFAULT_MAX_DEPTH
        timeout = timeout or _DEFAULT_TIMEOUT
        t0 = _t.perf_counter()

        # T009: 降级开关 — 关掉时只记录 fallback，不处理
        if not EVENT_ORCHESTRATOR_ENABLED:
            self._trace_depth.pop(event.trace_id or event.id, None)
            logger.debug(f"[orchestrator] fallback (disabled) for event={event.id}")
            return BrainCycleContext(event=event, error="orchestrator_disabled")

        # 深度保护
        trace_id = event.trace_id or event.id
        depth = self._trace_depth.get(trace_id, 0)
        if depth >= max_depth:
            logger.warning(
                f"[orchestrator] max depth reached for trace={trace_id} "
                f"depth={depth}, skipping event={event.id}"
            )
            ctx = BrainCycleContext(event=event, error="max_depth_reached")
            return ctx
        self._trace_depth[trace_id] = depth + 1

        # 预算保护（同一 trace 的 tool 回灌）
        budget = self._trace_budget.get(trace_id, 0)
        if budget >= _DEFAULT_BUDGET:
            logger.warning(
                f"[orchestrator] budget exhausted for trace={trace_id}"
            )
            ctx = BrainCycleContext(event=event, error="budget_exhausted")
            return ctx

        # 包装上下文
        ctx = BrainCycleContext(event=event)

        try:
            # Step 1: 感知 / 显著性
            ctx.perception = self._perceive(event, dry_run)

            # Step 2: 注意力
            ctx.attention = self._attend(event, ctx.perception, dry_run)

            # Step 3: 记忆召回（仅 chat / reflection 事件）
            if event.source in (EVENT_SOURCE_CHAT, EVENT_SOURCE_TOOL):
                ctx.memory = self._recall_memory(event, ctx.attention, dry_run)

            # Step 4: 状态更新
            ctx.state = self._update_state(event, ctx.memory, dry_run)

            # Step 5: 路由到处理器
            handler_results = route(event, ctx)
            ctx.action = {"handlers": len(handler_results), "results": handler_results}

            # 递增预算计数器（每次 tool 事件 +1，同一 trace 累计）
            if event.source == EVENT_SOURCE_TOOL:
                self._trace_budget[trace_id] = self._trace_budget.get(trace_id, 0) + 1

        except Exception as e:
            logger.warning(
                f"[orchestrator] process_event failed for "
                f"event={event.id}: {e}"
            )
            ctx.error = str(e)
        finally:
            elapsed = _t.perf_counter() - t0
            if elapsed > timeout:
                ctx.error = f"timeout ({elapsed:.1f}s > {timeout}s)"

            # 清理深度/预算计数器
            # tool 事件：30s 无活动则清理，防止长会话泄漏
            # 非 tool 事件：直接清理（chat/tick 是独立事件，不累积）
            if event.source == EVENT_SOURCE_TOOL:
                _now = _t.perf_counter()
                if not hasattr(self, "_trace_last_seen"):
                    self._trace_last_seen = {}
                _last = self._trace_last_seen.get(trace_id, 0)
                if _now - _last > 30.0:
                    self._trace_depth.pop(trace_id, None)
                    self._trace_budget.pop(trace_id, None)
                self._trace_last_seen[trace_id] = _now
            else:
                self._trace_depth.pop(trace_id, None)
                self._trace_budget.pop(trace_id, None)

        return ctx

    # ── 内部步骤 ─────────────────────────────────────────────
    def _perceive(self, event: BrainEvent, dry_run: bool) -> dict:
        """感知层：评估事件的基本属性。"""
        return {
            "source": event.source,
            "type": event.type,
            "modality": event.modality,
            "salience": event.salience,
            "content_length": len(event.content) if event.content else 0,
            "has_parent": bool(event.parent_id),
        }

    def _attend(self, event: BrainEvent, perception: dict, dry_run: bool) -> dict:
        """注意力层：决定事件的重要性和焦点。"""
        # 简单规则：chat 事件始终最高优先级，tool 结果次之
        if event.source == EVENT_SOURCE_CHAT:
            focus_level = 1.0
        elif event.source == EVENT_SOURCE_TOOL:
            focus_level = 0.8
        elif event.source == EVENT_SOURCE_TICK:
            focus_level = 0.4
        else:
            focus_level = 0.5

        return {
            "focus_level": focus_level,
            "focus_topic": event.content[:80] if event.content else "",
            "salience": perception.get("salience", 0.5),
        }

    def _recall_memory(self, event: BrainEvent, attention: dict, dry_run: bool) -> dict:
        """记忆层：根据事件内容搜索相关记忆。"""
        if dry_run or not event.content:
            return {"recalled": False, "items": []}

        # 只对有意义的内容做记忆召回（太短的 query 跳过）
        content = event.content.strip()
        if len(content) < 5:
            return {"recalled": False, "items": []}

        try:
            from main_brain.memory.core import search_memory

            # 用事件内容搜索相关记忆
            memories = search_memory(content)[:5]
            return {
                "recalled": bool(memories),
                "items": [
                    {"id": m.get("id", ""), "text": m.get("text", "")[:160], "score": m.get("score", 0)}
                    for m in memories
                ],
                "count": len(memories),
            }
        except Exception as e:
            logger.warning(f"[orchestrator] memory recall failed: {e}")
            return {"recalled": False, "items": [], "error": str(e)}

    def _update_state(self, event: BrainEvent, memory: dict, dry_run: bool) -> dict:
        """状态层：更新正在处理的焦点信息。"""
        if dry_run:
            return {"updated": False}

        try:
            from .adapters.state import get_state_adapter
            st = get_state_adapter()

            # 只更新 life_state 的 current_focus（轻量状态标记）
            focus = event.content[:40] if event.content else ""
            if focus and event.source == EVENT_SOURCE_CHAT:
                st.update_life_node({
                    "current_focus": focus,
                    "last_user_contact_at": _now_iso(),
                })
                return {"updated": True, "focus": focus}
        except Exception as e:
            logger.debug(f"[orchestrator] state update skipped: {e}")

        return {"updated": False}

    # ── 工具 ─────────────────────────────────────────────────
    def reset_trace(self, trace_id: str) -> None:
        """重置 trace 的深度/预算计数器（事件链结束时调用）。"""
        self._trace_depth.pop(trace_id, None)
        self._trace_budget.pop(trace_id, None)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
