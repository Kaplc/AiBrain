"""main_brain.testing — 测试与调试 harness（T020）

probe 函数支持 dry_run / mock，可绕过真实 LLM 做模块化测试（plan 第八节验收要求）。
不依赖 Flask 路由，可直接 import 使用。
"""
from .mocks import MockJudge, make_mock_decision
from .fixtures import build_life_test_context, sample_life_state, sample_candidate
from .harness import (
    test_judge_decision,
    run_cycle_probe,
    select_activity_probe,
    evaluate_gate_probe,
    build_life_test_context,
    snapshot_life_debug_state,
)

__all__ = [
    "MockJudge", "make_mock_decision",
    "build_life_test_context", "sample_life_state", "sample_candidate",
    "test_judge_decision", "run_cycle_probe", "select_activity_probe",
    "evaluate_gate_probe", "snapshot_life_debug_state",
]
