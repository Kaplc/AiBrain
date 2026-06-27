"""self_learn 话题选择（topic.py）单元测试

覆盖：
  - 缺口优先：从 open_loops 选 tension() 最高的 loop
  - 好奇心兜底：无缺口时从 goals / recent_thoughts 选
  - 无话题场景：全部空
  - 异常隔离：OpenLoopManager 不可用时优雅降级
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ── 缺口优先 ──────────────────────────────────────────────


class TestGapPriority:

    def test_selects_highest_tension_loop(self):
        """从多个 open_loops 中选 tension() 最高的 loop"""
        life = {
            "open_loops": [
                {"id": "L1", "content": "低优先级话题", "status": "open"},
                {"id": "L2", "content": "高优先级话题", "status": "open"},
            ]
        }
        with patch("main_brain.state.open_loops.OpenLoopManager") as MockMgr:
            mgr = MagicMock()
            MockMgr.return_value = mgr
            mgr.tension.side_effect = lambda loop: {"L1": 0.3, "L2": 0.9}.get(loop.get("id"), 0)

            from main_brain.self_learn.topic import select_topic
            topic, source, loop_id = select_topic(life)

        assert topic == "高优先级话题"
        assert source == "gap"
        assert loop_id == "L2"

    def test_filters_non_open_loops(self):
        """只考虑 status 为 open 或 None 的 loop"""
        life = {
            "open_loops": [
                {"id": "L1", "content": "已关闭", "status": "closed"},
                {"id": "L2", "content": "活跃中", "status": "open"},
                {"id": "L3", "content": "无状态", "status": None},
            ]
        }
        with patch("main_brain.state.open_loops.OpenLoopManager") as MockMgr:
            mgr = MagicMock()
            MockMgr.return_value = mgr
            mgr.tension.side_effect = lambda loop: {"L1": 0, "L2": 0.5, "L3": 0.2}.get(loop.get("id"), 0)

            from main_brain.self_learn.topic import select_topic
            topic, source, loop_id = select_topic(life)

        # 跳过 L1 (closed)，L2 tension 最高
        assert topic == "活跃中"

    def test_uses_node_ids_when_content_empty(self):
        """loop 无 content 时用 node_ids[0] 代替"""
        life = {
            "open_loops": [
                {"id": "L1", "content": "", "node_ids": ["node_abc"], "status": "open"},
            ]
        }
        with patch("main_brain.state.open_loops.OpenLoopManager") as MockMgr:
            mgr = MagicMock()
            MockMgr.return_value = mgr
            mgr.tension.return_value = 1.0

            from main_brain.self_learn.topic import select_topic
            topic, source, loop_id = select_topic(life)

        assert topic == "node_abc"
        assert source == "gap"
        assert loop_id == "L1"

    def test_returns_empty_when_no_valid_loops(self):
        """所有 loop 都 closed → 降级到 curiosity"""
        life = {
            "open_loops": [
                {"id": "L1", "content": "被关闭", "status": "closed"},
            ],
            "goals": [],
            "recent_thoughts": [],
        }
        with patch("main_brain.state.open_loops.OpenLoopManager") as MockMgr:
            mgr = MagicMock()
            MockMgr.return_value = mgr
            mgr.tension.return_value = 0.0

            from main_brain.self_learn.topic import select_topic
            topic, source, loop_id = select_topic(life)

        assert topic == ""
        assert source == ""

    def test_open_loop_exception_does_not_block(self):
        """OpenLoopManager.tension 抛异常时单条降级 0，不阻断整批"""
        life = {
            "open_loops": [
                {"id": "L1", "content": "异常话题", "status": "open"},
                {"id": "L2", "content": "正常话题", "status": "open"},
            ]
        }
        with patch("main_brain.state.open_loops.OpenLoopManager") as MockMgr:
            mgr = MagicMock()
            MockMgr.return_value = mgr
            mgr.tension.side_effect = [ValueError("模拟异常"), 0.8]

            from main_brain.self_learn.topic import select_topic
            topic, source, loop_id = select_topic(life)

        assert topic == "正常话题"
        assert source == "gap"

    def test_no_open_loops_key(self):
        """life_state 无 open_loops 键，不抛异常，降级 curiosity"""
        life = {"goals": [], "recent_thoughts": []}

        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert topic == ""
        assert source == ""


# ── 好奇心兜底 ──────────────────────────────────────────


class TestCuriosityFallback:

    def test_uses_goal_name(self):
        """无 open_loops 时从 goals 的 name 选话题"""
        life = {
            "open_loops": [],
            "goals": [
                {"name": "学习 Python 异步编程", "description": "掌握 asyncio"},
            ],
            "recent_thoughts": [],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert topic == "学习 Python 异步编程"
        assert source == "curiosity"
        assert loop_id is None

    def test_uses_goal_description_when_name_empty(self):
        """goal 有 description 但无 name 时用 description"""
        life = {
            "open_loops": [],
            "goals": [
                {"name": "", "description": "掌握 FastAPI 并发处理"},
            ],
            "recent_thoughts": [],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert topic == "掌握 FastAPI 并发处理"
        assert source == "curiosity"

    def test_uses_first_goal(self):
        """多个 goals 时选第一个非空 goal"""
        life = {
            "open_loops": [],
            "goals": [
                {"name": "", "description": ""},
                {"name": "第二个目标", "description": "有效目标"},
                {"name": "第三个", "description": ""},
            ],
            "recent_thoughts": [],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert topic == "第二个目标"
        assert source == "curiosity"

    def test_uses_recent_thoughts_when_no_goals(self):
        """无 goals 时从 recent_thoughts 取最新一条（长度 > 10）"""
        life = {
            "open_loops": [],
            "goals": [],
            "recent_thoughts": [
                "短",
                "这是一条足够长的思考内容，可以作为学习话题",
            ],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert "足够长的思考内容" in topic
        assert source == "curiosity"

    def test_recent_thoughts_dict_format(self):
        """recent_thoughts 中的 dict 用 summary 字段"""
        life = {
            "open_loops": [],
            "goals": [],
            "recent_thoughts": [
                {"summary": "从字典格式提取的长话题内容"},
            ],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert "从字典格式" in topic

    def test_recent_thoughts_skips_short_entries(self):
        """跳过长度 ≤ 10 的思考条目"""
        life = {
            "open_loops": [],
            "goals": [],
            "recent_thoughts": [
                "太短了",
                "这条足够长了，可以作为学习话题使用",
            ],
        }
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic(life)

        assert "足够长了" in topic

    def test_truncates_to_200_chars(self):
        """话题截断到 200 字符"""
        long_text = "话题" * 200
        life = {
            "open_loops": [],
            "goals": [{"name": long_text, "description": ""}],
            "recent_thoughts": [],
        }
        from main_brain.self_learn.topic import select_topic
        topic, _, _ = select_topic(life)

        assert len(topic) <= 200


# ── 全空场景 ────────────────────────────────────────────


class TestNoTopic:

    def test_all_empty(self):
        """所有来源都空时返回 ("", "", None)"""
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic({})

        assert topic == ""
        assert source == ""
        assert loop_id is None

    def test_empty_loops_and_empty_goals_and_no_thoughts(self):
        """明确空列表而非缺失 key"""
        from main_brain.self_learn.topic import select_topic
        topic, source, loop_id = select_topic({
            "open_loops": [],
            "goals": [],
            "recent_thoughts": [],
        })
        assert topic == ""
