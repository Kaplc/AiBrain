"""mocks — MockJudge / 构造假决策，绕过真实 LLM 做稳定测试。"""
from __future__ import annotations

from typing import Any

from ..contracts import BrainJudgeDecision, REACTIVE, BACKGROUND
from ..judge import JudgeResult


def make_mock_decision(**kwargs) -> dict:
    """构造一份 mock judge 原始 dict（模拟 LLM 输出），供 test_judge_decision。"""
    base = {
        "thought_summary": "测试决策",
        "mode": REACTIVE,
        "focus": "测试焦点",
        "next_action": "final_reply",
        "action_args": {},
        "state_updates": {},
        "pending_expression": {},
        "reply_strategy": {"tone": "轻松", "key_points": ["测试"]},
        "should_notify_user": False,
        "notify_reason": "",
        "learning_hints": ["测试经验"],
        "confidence": 0.8,
    }
    base.update(kwargs)
    return base


class MockJudge:
    """按预设队列/固定返回决策的假 judge，供 run_cycle_probe 用。

    decisions: 依次返回的 BrainJudgeDecision 列表；用完返回最后一个。
    """

    def __init__(self, decisions: list[BrainJudgeDecision] | None = None,
                 raw_dicts: list[dict] | None = None):
        if raw_dicts:
            decisions = [BrainJudgeDecision.from_dict(d) for d in raw_dicts]
        self._decisions = decisions or [BrainJudgeDecision(next_action="sleep")]
        self._idx = 0
        self.calls = 0

    def decide(self, view: dict, mode: str = REACTIVE, activity: str = "",
               *, mock_response: str | None = None) -> JudgeResult:
        self.calls += 1
        d = self._decisions[min(self._idx, len(self._decisions) - 1)]
        self._idx += 1
        d.mode = mode
        return JudgeResult(decision=d, schema_valid=True, latency_ms=5.0)

    def reset(self):
        self._idx = 0
        self.calls = 0
