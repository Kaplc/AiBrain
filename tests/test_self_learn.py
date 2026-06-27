"""self_learn 主编排（__init__.py）单元测试

覆盖：
  - Guard 总开关 / 每日上限
  - select_topic 空结果
  - Cooldown 检查
  - dry_run 模式
  - 全流程（gap 和 curiosity 两种来源）
  - 每个外部依赖异常时的优雅降级
  - _today_count 辅助函数

注意：run_self_learn 使用懒导入（from X import Y 在函数体内），
所以 patch 必须打在懒导入的元位置（module.attr），而非 self_learn 包。
"""
import hashlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_TOPIC = "Python异步编程"
_TOPIC_HASH = hashlib.md5(_TOPIC.encode()).hexdigest()[:12]

# 预导入，使 lazy import 能正确找到 patch 后的属性
import main_brain.state.times
import main_brain.state.expression_history
import main_brain.config
import main_brain.memory.core
import main_brain.state.open_loops
import main_brain.adapters.learning


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def base_cfg():
    """基础配置：self_learn 开启"""
    return {
        "self_learn_enabled": True,
        "self_learn_max_per_day": 3,
        "self_learn_cooldown_hours": 12,
        "self_learn_max_chars_per_topic": 3000,
    }


@pytest.fixture
def mock_eh_mgr():
    """模拟 expression_history manager，使 _today_count 返回 0"""
    mgr = MagicMock()
    mgr.is_in_refractory.return_value = False  # 不在冷却中
    # _today_count 会调 mgr._state.snapshot()
    mgr._state = MagicMock()
    mgr._state.snapshot.return_value = {"expression_history": []}
    return mgr


@pytest.fixture
def default_tick_input():
    """标准 TickInput 兼容 dict"""
    return {
        "life_state": {
            "open_loops": [],
            "goals": [{"name": "学习目标", "description": ""}],
            "recent_thoughts": [],
        },
        "tool_context": {},
        "recent_runs": [],
        "tick_type": "medium",
    }


@pytest.fixture
def success_patches(base_cfg, mock_eh_mgr):
    """最基本的成功 mock 集合 — 所有依赖都正常工作"""
    patches = [
        patch("main_brain.config.get_brain_config", return_value=base_cfg),
        patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
        patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
        patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
        patch("main_brain.self_learn.search_and_digest", return_value="摘要内容"),
        patch("main_brain.memory.core.store_memory", return_value={"memory_id": "mem_001"}),
        patch("main_brain.adapters.learning.get_learning_adapter"),
    ]
    return patches


# ── Guard：总开关 ───────────────────────────────────────


class TestGuardDisabled:

    def test_returns_skipped_when_disabled(self, default_tick_input):
        """self_learn_enabled=False → skipped"""
        cfg = {"self_learn_enabled": False}
        with patch("main_brain.config.get_brain_config", return_value=cfg):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result == {"ok": False, "skipped": True, "reason": "self_learn_disabled"}


# ── Guard：每日上限 ─────────────────────────────────────


class TestGuardDailyCap:

    def test_returns_skipped_when_at_cap(self, base_cfg, default_tick_input):
        """今日已达上限 → skipped"""
        # mock _today_count 返回 3（对 expression_history 打桩让其 snapshot 返回 3 条今日记录）
        mock_mgr = MagicMock()
        mock_mgr.is_in_refractory.return_value = False
        mock_mgr._state = MagicMock()
        mock_mgr._state.snapshot.return_value = {
            "expression_history": [
                {"expression_type": "self_learn", "last_expressed": "2026-06-27T10:00:00"},
                {"expression_type": "self_learn", "last_expressed": "2026-06-27T11:00:00"},
                {"expression_type": "self_learn", "last_expressed": "2026-06-27T12:00:00"},
            ]
        }
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T12:30:00"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result == {"ok": False, "skipped": True, "reason": "max_per_day_reached"}

    def test_under_cap_proceeds(self, base_cfg, default_tick_input, mock_eh_mgr):
        """今日未达上限 → 继续执行"""
        base_cfg["self_learn_max_per_day"] = 5
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=("话题", "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="内容摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "mem_001"}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True


# ── 无话题 ──────────────────────────────────────────────


class TestNoTopic:

    def test_returns_skipped_when_no_topic(self, base_cfg, default_tick_input, mock_eh_mgr):
        """select_topic 返空 → skipped"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=("", "", None)),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result == {"ok": False, "skipped": True, "reason": "no_topic"}


# ── Cooldown ────────────────────────────────────────────


class TestCooldown:

    def test_skipped_when_in_cooldown(self, base_cfg, default_tick_input, mock_eh_mgr):
        """topic 在冷却期 → skipped"""
        mock_eh_mgr.is_in_refractory.return_value = True
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "gap", "L1")),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result == {"ok": False, "skipped": True, "reason": "topic_in_cooldown"}

    def test_cooldown_check_skipped_on_error(self, base_cfg, default_tick_input):
        """cooldown 检查抛异常 → 跳过冷却检查继续执行"""
        mock_mgr = MagicMock()
        mock_mgr._state = MagicMock()
        mock_mgr._state.snapshot.return_value = {"expression_history": []}
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "mem_001"}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            # is_in_refractory 抛出异常
            mock_mgr.is_in_refractory.side_effect = RuntimeError("模拟异常")
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True


# ── Dry Run ─────────────────────────────────────────────


class TestDryRun:

    def test_dry_run_returns_topic_no_side_effects(self, base_cfg, default_tick_input, mock_eh_mgr):
        """dry_run=True 返回话题信息，不执行搜索/存储"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "gap", "L1")),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input, dry_run=True)

        assert result == {
            "ok": True,
            "dry_run": True,
            "topic": _TOPIC,
            "source": "gap",
            "loop_id": "L1",
            "cooldown_key": _TOPIC_HASH,
        }

    def test_dry_run_does_not_call_search(self, base_cfg, default_tick_input, mock_eh_mgr):
        """dry_run 确保 search_and_digest 不被调用"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest") as mock_search,
        ):
            from main_brain.self_learn import run_self_learn
            run_self_learn(default_tick_input, dry_run=True)

        mock_search.assert_not_called()


# ── 全流程成功 ──────────────────────────────────────────


class TestFullSuccess:

    def test_gap_source_calls_add_thought(self, base_cfg, default_tick_input, mock_eh_mgr):
        """gap 来源 → store_memory + add_thought + cooldown record + sink_hints"""
        mock_adapter = MagicMock()
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "gap", "L1")),
            patch("main_brain.self_learn.search_and_digest", return_value="关于Python异步编程的详细摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "mem_001"}) as mock_store,
            patch("main_brain.state.open_loops.OpenLoopManager") as MockOlm,
            patch("main_brain.adapters.learning.get_learning_adapter", return_value=mock_adapter),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        # 验证结果
        assert result["ok"] is True
        assert result["topic"] == _TOPIC
        assert result["source"] == "gap"
        assert result["loop_id"] == "L1"

        # 验证 store_memory 调用
        mock_store.assert_called_once()
        store_args = mock_store.call_args
        assert store_args[0][0] == "关于Python异步编程的详细摘要"
        assert store_args[1]["memory_meta"]["source"] == "self_learn"
        assert store_args[1]["memory_meta"]["topic"] == _TOPIC

        # 验证 add_thought 调用
        MockOlm.assert_called_once()
        MockOlm.return_value.add_thought.assert_called_once_with("L1")

        # 验证 cooldown record
        mock_eh_mgr.record.assert_called_once_with("self_learn", _TOPIC_HASH, hours=12)

        # 验证 sink_hints
        mock_adapter.sink_hints.assert_called_once()
        sunk = mock_adapter.sink_hints.call_args[0][0]
        assert _TOPIC in sunk[0]

    def test_curiosity_source_skips_add_thought(self, base_cfg, default_tick_input, mock_eh_mgr):
        """curiosity 来源 → 不调 add_thought"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=("学习话题", "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "mem_002"}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True
        assert result["source"] == "curiosity"

    def test_store_memory_returns_memory_id(self, base_cfg, default_tick_input, mock_eh_mgr):
        """store_memory 返回值被截断后写入 result.stored"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="内容"),
            patch("main_brain.memory.core.store_memory", return_value={"result": "已记住: 新增 1 条记忆", "added_count": 1, "stored_texts": ["内容"]}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["stored"] == "ok+1"
        assert result["summary_len"] == 2

    def test_empty_summary_uses_topic_as_fallback(self, base_cfg, default_tick_input, mock_eh_mgr):
        """摘要为空时用 topic 本身（'关于「{topic}」'）作为记忆内容"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value=""),
            patch("main_brain.memory.core.store_memory") as mock_store,
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            run_self_learn(default_tick_input)

        stored_text = mock_store.call_args[0][0]
        assert "Python异步编程" in stored_text

    def test_tick_input_dataclass_compatible(self, base_cfg, mock_eh_mgr):
        """兼容 TickInput dataclass（有 life_state 属性）"""
        tick_input = SimpleNamespace()
        tick_input.life_state = {
            "open_loops": [],
            "goals": [{"name": "学习", "description": ""}],
            "recent_thoughts": [],
        }
        tick_input.tool_context = {}
        tick_input.recent_runs = []
        tick_input.tick_type = "medium"

        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=("话题", "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "m1"}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(tick_input)

        assert result["ok"] is True


# ── 异常降级 ────────────────────────────────────────────


class TestErrorResilience:

    def test_store_memory_failure(self, base_cfg, default_tick_input, mock_eh_mgr):
        """store_memory 抛异常 → stored 为空，不影响后续 feedback"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要内容"),
            patch("main_brain.memory.core.store_memory", side_effect=RuntimeError("存储异常")),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True
        assert result["stored"] == ""

    def test_add_thought_failure_does_not_block(self, base_cfg, default_tick_input, mock_eh_mgr):
        """add_thought 抛异常 → 仅 log 警告，继续执行"""
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "gap", "L1")),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "m1"}),
            patch("main_brain.state.open_loops.OpenLoopManager") as MockOlm,
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            MockOlm.side_effect = RuntimeError("模拟异常")
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True

    def test_record_cooldown_failure_does_not_block(self, base_cfg, default_tick_input, mock_eh_mgr):
        """record cooldown 抛异常 → 仅 log 警告"""
        mock_eh_mgr.record.side_effect = RuntimeError("记录异常")
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "m1"}),
            patch("main_brain.adapters.learning.get_learning_adapter"),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True

    def test_sink_hints_failure_does_not_block(self, base_cfg, default_tick_input, mock_eh_mgr):
        """sink_hints 抛异常 → 仅 log 警告"""
        mock_adapter = MagicMock()
        mock_adapter.sink_hints.side_effect = RuntimeError("sink 异常")
        with (
            patch("main_brain.config.get_brain_config", return_value=base_cfg),
            patch("main_brain.state.get_expression_history", return_value=mock_eh_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T10:00:00"),
            patch("main_brain.self_learn.select_topic", return_value=(_TOPIC, "curiosity", None)),
            patch("main_brain.self_learn.search_and_digest", return_value="摘要"),
            patch("main_brain.memory.core.store_memory", return_value={"memory_id": "m1"}),
            patch("main_brain.adapters.learning.get_learning_adapter", return_value=mock_adapter),
        ):
            from main_brain.self_learn import run_self_learn
            result = run_self_learn(default_tick_input)

        assert result["ok"] is True


# ── _today_count 辅助函数 ───────────────────────────────


class TestTodayCount:

    def test_counts_today_only(self):
        """_today_count 只统计当天日期的记录"""
        mock_mgr = MagicMock()
        mock_mgr._state = MagicMock()
        mock_mgr._state.snapshot.return_value = {
            "expression_history": [
                # 今天
                {"expression_type": "self_learn", "last_expressed": "2026-06-27T08:00:00"},
                # 昨天
                {"expression_type": "self_learn", "last_expressed": "2026-06-26T20:00:00"},
                # 非 self_learn
                {"expression_type": "reflect", "last_expressed": "2026-06-27T09:00:00"},
            ]
        }
        with (
            patch("main_brain.state.get_expression_history", return_value=mock_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T12:00:00"),
        ):
            from main_brain.self_learn import _today_count
            assert _today_count() == 1

    def test_returns_zero_on_error(self):
        """_today_count 抛异常时返回 0"""
        with patch("main_brain.state.get_expression_history", side_effect=Exception("模拟异常")):
            from main_brain.self_learn import _today_count
            assert _today_count() == 0

    def test_returns_zero_on_empty(self):
        """expression_history 为空时返回 0"""
        mock_mgr = MagicMock()
        mock_mgr._state = MagicMock()
        mock_mgr._state.snapshot.return_value = {"expression_history": []}
        with (
            patch("main_brain.state.get_expression_history", return_value=mock_mgr),
            patch("main_brain.state.times.now_iso", return_value="2026-06-27T12:00:00"),
        ):
            from main_brain.self_learn import _today_count
            assert _today_count() == 0
