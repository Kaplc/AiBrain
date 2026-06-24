"""事件路由 — 按 source/type 分发到对应处理器（T002 / FR-002）

每个 event source 注册一个 handler chain，orchestrator 调用 route(event) 获取
处理器列表。注册机制支持第一版只记录不处理（兼容旧链路）。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .contracts import BrainEvent, BrainCycleContext

logger = logging.getLogger("main_brain.router")

EventHandler = Callable[[BrainEvent, BrainCycleContext], Optional[dict]]

# 全局注册表：source -> [(type_pattern, handler)]
_ROUTER_REGISTRY: dict[str, list[tuple[str, EventHandler]]] = {}


def register(source: str, type_pattern: str, handler: EventHandler) -> None:
    """注册事件处理器。

    Args:
        source: 事件来源（EVENT_SOURCE_*）
        type_pattern: 事件类型（EVENT_TYPE_*），或 "*" 匹配所有
        handler: 处理函数 (event, ctx) -> dict | None
    """
    if source not in _ROUTER_REGISTRY:
        _ROUTER_REGISTRY[source] = []
    _ROUTER_REGISTRY[source].append((type_pattern, handler))
    logger.info(
        f"[router] registered handler: source={source} type={type_pattern} "
        f"handler={handler.__name__}"
    )


def unregister(source: str, handler: EventHandler) -> None:
    """取消注册处理器。"""
    handlers = _ROUTER_REGISTRY.get(source, [])
    _ROUTER_REGISTRY[source] = [
        (tp, h) for tp, h in handlers if h is not handler
    ]


def route(event: BrainEvent, ctx: BrainCycleContext) -> list[dict]:
    """将事件路由到所有匹配的处理器，返回处理结果列表。

    按注册顺序执行。任一处理器返回异常不会影响后续处理器。

    Returns:
        list[dict]: 每个 handler 的输出（可能为空）
    """
    source_handlers = _ROUTER_REGISTRY.get(event.source, [])
    if not source_handlers:
        logger.debug(f"[router] no handlers for source={event.source}")
        return []

    results = []
    for type_pattern, handler in source_handlers:
        if type_pattern != "*" and type_pattern != event.type:
            continue
        try:
            result = handler(event, ctx)
            if result is not None:
                results.append(result)
        except Exception as e:
            logger.warning(
                f"[router] handler {handler.__name__} failed for "
                f"event={event.id}: {e}"
            )
            ctx.error = str(e)
    return results


# ── 默认处理器注册 ──────────────────────────────────────────
# 在 orchestrator 初始化时调用
def register_default_handlers() -> None:
    """注册默认事件处理器（日志型：只记录，不做事）。

    每个 source 至少有一个 fallback 处理器，确保事件不会被静默丢弃。
    具体业务逻辑在第三阶段由具体模块注册。
    """
    from .logging.event_log import get_event_log

    def _log_only(event: BrainEvent, ctx: BrainCycleContext) -> dict:
        """默认处理器：只记录事件到日志，不产生副作用。"""
        get_event_log().append_event(event.to_dict())
        return {"logged": True}

    # 所有来源都注册 * 通配符处理器（兜底记录）
    for source in (
        "chat", "tool", "tick", "reflection",
        "system", "file", "vision",
    ):
        register(source, "*", _log_only)

    logger.info("[router] default handlers registered (log-only)")


# ── 清空注册表（测试用） ─────────────────────────────────────
def _clear():
    _ROUTER_REGISTRY.clear()
