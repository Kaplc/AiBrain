"""EventBus — 全局事件总线（发布/订阅）

放在 core/ 层，所有模块（main_brain、modules/*、routes/*）平等依赖，
不产生依赖方向问题。

用法:
    from core.event_bus import get_event_bus

    # 发事件
    get_event_bus().emit("self_learn", "completed", {"topic": "..."})

    # 订阅
    def handler(ev):
        print(f"{ev.source}.{ev.type}: {ev.data}")

    get_event_bus().on("*", "*", handler)          # 所有事件
    get_event_bus().on("self_learn", "*", handler) # 某来源
    get_event_bus().off("*", "*", handler)          # 取消
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("event_bus")


@dataclass
class Event:
    """一条总线事件。"""
    source: str                     # 来源，如 "self_learn", "tick", "chat"
    type: str                       # 类型，如 "completed", "started", "error"
    data: dict = field(default_factory=dict)  # 自由格式载荷
    timestamp: str = ""             # ISO 时间，emit 时自动填充


# 订阅者签名: Callable[[Event], None]
_Handler = Callable[["Event"], None]


class EventBus:
    """全局事件总线 — 发布/订阅，解耦跨模块通信。

    线程安全，订阅者异常不会阻断其他订阅者。
    """

    def __init__(self):
        self._lock = threading.Lock()
        # key: "source:type" → list[handler]
        self._subscribers: dict[str, list[_Handler]] = {}

    # ── 发射 ───────────────────────────────────────────────

    def emit(self, source: str, type: str, data: dict = None) -> None:
        """发射事件，通知所有匹配的订阅者。

        匹配规则：
          - 精确匹配 "source:type"
          - 通配匹配 "*:type"、"source:*"、"*:*"
        """
        import json
        from datetime import datetime, timezone

        event = Event(
            source=source,
            type=type,
            data=data or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        logger.debug(f"[emit] {source}.{type} | data={json.dumps(data, ensure_ascii=False)[:200]}")

        handlers = self._resolve(source, type)
        for fn in handlers:
            try:
                fn(event)
            except Exception as e:
                logger.warning(f"[emit] handler {fn.__name__} failed: {e}")

    # ── 订阅 / 取消 ────────────────────────────────────────

    def on(self, source: str, type: str, handler: _Handler) -> None:
        """订阅事件。source/type 支持 "*" 通配符。"""
        key = self._key(source, type)
        with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            if handler not in self._subscribers[key]:
                self._subscribers[key].append(handler)
                logger.debug(f"[on] {key} | handler={handler.__name__}")

    def off(self, source: str, type: str, handler: _Handler) -> None:
        """取消订阅。参数必须与 on() 时的 source/type/handler 一致。"""
        key = self._key(source, type)
        with self._lock:
            if key in self._subscribers:
                self._subscribers[key] = [h for h in self._subscribers[key] if h is not handler]
                if not self._subscribers[key]:
                    del self._subscribers[key]
                logger.debug(f"[off] {key} | handler={handler.__name__}")

    # ── 内部 ───────────────────────────────────────────────

    @staticmethod
    def _key(source: str, type: str) -> str:
        return f"{source}:{type}"

    def _resolve(self, source: str, type: str) -> list[_Handler]:
        """解析匹配 source/type 的所有订阅者（含通配）。"""
        keys = [
            self._key(source, type),   # 精确匹配
            self._key("*", type),       # 通配来源
            self._key(source, "*"),     # 通配类型
            self._key("*", "*"),        # 通配全部
        ]
        seen: set[int] = set()
        result: list[_Handler] = []
        with self._lock:
            for k in keys:
                for fn in self._subscribers.get(k, []):
                    fid = id(fn)
                    if fid not in seen:
                        seen.add(fid)
                        result.append(fn)
        return result

    def count(self) -> int:
        """当前订阅总数（调试用）。"""
        with self._lock:
            return sum(len(v) for v in self._subscribers.values())

    def clear(self) -> None:
        """清空所有订阅（测试用）。"""
        with self._lock:
            self._subscribers.clear()


# ── 单例 ───────────────────────────────────────────────────

_bus: EventBus = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """测试用：重置单例并清空订阅。"""
    global _bus
    with _bus_lock:
        if _bus is not None:
            _bus.clear()
        _bus = None
