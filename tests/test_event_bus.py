"""EventBus 单元测试

覆盖：
  - emit/on/off 基本功能
  - 通配符匹配（*:*, source:*, *:type, source:type）
  - 异常隔离（坏 handler 不崩其他）
  - 去重（同一 handler 重复注册只调一次）
  - reset 和 clear
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture(autouse=True)
def reset_bus():
    """每个测试前重置 EventBus 单例。"""
    from core.event_bus import reset_event_bus
    reset_event_bus()
    yield
    reset_event_bus()


def _make_bus():
    from core.event_bus import EventBus
    return EventBus()


# ── 基本功能 ──────────────────────────────────────────


class TestBasicEmitOn:

    def test_on_and_emit(self):
        """注册 handler 后 emit 能收到事件。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append((ev.source, ev.type, ev.data))

        bus.on("test", "done", handler)
        bus.emit("test", "done", {"key": "val"})

        assert len(received) == 1
        src, typ, data = received[0]
        assert src == "test"
        assert typ == "done"
        assert data == {"key": "val"}

    def test_off_cancels_handler(self):
        """取消订阅后不再收到事件。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(ev)

        bus.on("a", "b", handler)
        bus.off("a", "b", handler)
        bus.emit("a", "b")

        assert len(received) == 0

    def test_timestamp_auto_filled(self):
        """emit 时自动填充 ISO 时间戳。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(ev.timestamp)

        bus.on("*", "*", handler)
        bus.emit("x", "y")

        assert len(received) == 1
        assert received[0].startswith("202")  # ISO 时间

    def test_multiple_handlers_same_event(self):
        """同一事件可注册多个 handler。"""
        bus = _make_bus()
        results = []

        def h1(ev): results.append("h1")
        def h2(ev): results.append("h2")

        bus.on("t", "e", h1)
        bus.on("t", "e", h2)
        bus.emit("t", "e")

        assert sorted(results) == ["h1", "h2"]


# ── 通配符 ────────────────────────────────────────────


class TestWildcard:

    def test_wildcard_all(self):
        """*:* 匹配所有事件。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(f"{ev.source}.{ev.type}")

        bus.on("*", "*", handler)
        bus.emit("src1", "type1")
        bus.emit("src2", "type2")

        assert "src1.type1" in received
        assert "src2.type2" in received

    def test_wildcard_source(self):
        """source:* 匹配某来源的所有类型。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(f"{ev.source}.{ev.type}")

        bus.on("chat", "*", handler)
        bus.emit("chat", "message")
        bus.emit("chat", "reaction")
        bus.emit("system", "tick")  # 不应匹配

        assert "chat.message" in received
        assert "chat.reaction" in received
        assert "system.tick" not in received

    def test_wildcard_type(self):
        """*:type 匹配所有来源的某类型。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(f"{ev.source}.{ev.type}")

        bus.on("*", "completed", handler)
        bus.emit("self_learn", "completed")
        bus.emit("tick", "completed")
        bus.emit("self_learn", "started")  # 不应匹配

        assert "self_learn.completed" in received
        assert "tick.completed" in received
        assert "self_learn.started" not in received

    def test_wildcard_no_duplicate(self):
        """一个 handler 同时匹配多条规则时不重复调用。"""
        bus = _make_bus()
        count = 0

        def handler(ev):
            nonlocal count
            count += 1

        bus.on("*", "*", handler)      # 匹配所有
        bus.on("test", "*", handler)    # 也匹配 test.*
        bus.on("*", "event", handler)   # 也匹配 *.event
        bus.emit("test", "event")

        assert count == 1  # 只调一次


# ── 异常隔离 ──────────────────────────────────────────


class TestErrorIsolation:

    def test_bad_handler_does_not_block_others(self):
        """抛异常的 handler 不阻断其他 handler。"""
        bus = _make_bus()
        results = []

        def bad(ev):
            raise RuntimeError("boom")

        def good(ev):
            results.append("ok")

        bus.on("t", "e", bad)
        bus.on("t", "e", good)
        bus.emit("t", "e")

        assert results == ["ok"]

    def test_bad_handler_does_not_block_later_events(self):
        """坏的 handler 不阻断后续 emit。"""
        bus = _make_bus()
        results = []

        def bad(ev):
            raise RuntimeError("boom")

        def good(ev):
            results.append(ev.type)

        bus.on("*", "*", bad)
        bus.on("*", "*", good)

        bus.emit("t", "first")
        bus.emit("t", "second")

        assert results == ["first", "second"]


# ── 去重 ──────────────────────────────────────────────


class TestDedup:

    def test_same_handler_registered_once(self):
        """同一 handler 重复注册只执行一次。"""
        bus = _make_bus()
        count = 0

        def handler(ev):
            nonlocal count
            count += 1

        bus.on("x", "y", handler)
        bus.on("x", "y", handler)  # 重复注册
        bus.emit("x", "y")

        assert count == 1

    def test_same_handler_different_wildcards_once(self):
        """同一 handler 通过不同通配符注册也只执行一次。"""
        bus = _make_bus()
        count = 0

        def handler(ev):
            nonlocal count
            count += 1

        bus.on("*", "*", handler)
        bus.on("x", "*", handler)  # 通配会解析到同一个 handler
        bus.emit("x", "y")

        assert count == 1


# ── 单例 ──────────────────────────────────────────────


class TestSingleton:

    def test_get_event_bus_returns_same(self):
        """get_event_bus() 返回同一个实例。"""
        from core.event_bus import get_event_bus
        a = get_event_bus()
        b = get_event_bus()
        assert a is b

    def test_reset_clears_subscribers(self):
        """reset_event_bus() 清空订阅。"""
        from core.event_bus import get_event_bus, reset_event_bus

        bus = get_event_bus()
        bus.on("*", "*", lambda ev: None)
        assert bus.count() == 1

        reset_event_bus()
        assert get_event_bus().count() == 0

    def test_clear(self):
        """clear() 清空订阅。"""
        bus = _make_bus()
        bus.on("a", "b", lambda ev: None)
        bus.on("c", "d", lambda ev: None)
        assert bus.count() == 2
        bus.clear()
        assert bus.count() == 0


# ── data 默认值 ──────────────────────────────────────


class TestDataDefault:

    def test_emit_without_data(self):
        """不传 data 时默认空 dict。"""
        bus = _make_bus()
        received = []

        def handler(ev):
            received.append(ev.data)

        bus.on("*", "*", handler)
        bus.emit("s", "t")

        assert received == [{}]
