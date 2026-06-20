"""最小集成测试（T022）— 覆盖 reactive / life tick / activity selection / gate hold+send / fallback。

用 mock_decision / mock_response 绕过真实 LLM，dry_run 不写状态。
运行：
    cd backend && python -m main_brain.testing.integration_test
"""
from __future__ import annotations

import json
import sys

from . import (
    build_life_test_context, sample_life_state, sample_candidate,
    test_judge_decision, run_cycle_probe, select_activity_probe,
    evaluate_gate_probe, snapshot_life_debug_state,
)
from ..contracts import REACTIVE, BACKGROUND, TICK_MEDIUM, TICK_SHORT


_passed = 0
_failed = 0


def _check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name} {detail}")


def test_reactive_session_routing():
    print("\n[1] Reactive session 路由（recall_memory -> final_reply）")
    ctx = build_life_test_context(mode=REACTIVE, tick_type="")
    res = run_cycle_probe(
        ctx,
        mock_decisions=[
            {"next_action": "recall_memory", "action_args": {"query": "记忆"},
             "thought_summary": "查记忆", "focus": "memory", "confidence": 0.7},
            {"next_action": "final_reply", "thought_summary": "好了",
             "focus": "memory", "confidence": 0.9,
             "reply_strategy": {"tone": "认真", "key_points": ["a"]}},
        ],
        dry_run=True,
    )
    _check("ok", res["ok"], str(res.get("errors")))
    _check("actions 序列正确", res["actions"] == ["recall_memory", "final_reply"],
           str(res["actions"]))
    _check("stop_reason=ready", res["stop_reason"] == "ready", res["stop_reason"])
    _check("cycle_count=2", res["cycle_count"] == 2, str(res["cycle_count"]))


def test_life_tick_dry_run():
    print("\n[2] Life tick dry_run（background sleep）")
    ctx = build_life_test_context(mode=BACKGROUND, tick_type=TICK_MEDIUM,
                                  life_state=sample_life_state(idle_seconds=100))
    res = run_cycle_probe(ctx, mock_decision={"next_action": "sleep", "confidence": 0.5},
                          dry_run=True)
    _check("ok", res["ok"])
    _check("stop_reason=sleep", res["stop_reason"] == "sleep", res["stop_reason"])
    _check("不产生副作用（无 recall/update）",
           not any(a in ("recall_memory", "update_state") for a in res["actions"]),
           str(res["actions"]))


def test_activity_selection():
    print("\n[3] ActivitySelector 选择")
    # 短 tick → wait
    r = select_activity_probe(sample_life_state(), TICK_SHORT)
    _check("short_tick→wait", r["selected_activity"] == "wait", r["selected_activity"])
    # observe → wait
    r = select_activity_probe(sample_life_state(idle_seconds=1000), TICK_MEDIUM,
                              autonomy_level="observe")
    _check("observe→wait", r["selected_activity"] == "wait", r["reason"])
    # 空闲+有 pending → proactive_contact
    r = select_activity_probe(
        sample_life_state(idle_seconds=900, pending_expressions=[{"x": 1}]),
        TICK_MEDIUM, pending_expressions=[{"x": 1}], autonomy_level="assist")
    _check("空闲+pending→proactive_contact",
           r["selected_activity"] == "proactive_contact", r["reason"])


def test_gate_hold_and_send():
    print("\n[4] ExpressionGate hold / suppress（proactive 默认关→suppress）")
    life = sample_life_state(idle_seconds=2000, last_proactive_contact_at="")
    # proactive 关：suppress
    r = evaluate_gate_probe(sample_candidate(value=0.9), life)
    _check("proactive 关→suppress", r["gate"].get("action") == "suppress",
           r["gate"].get("reason"))
    # 正在聊天 → interruption 拉满，即便开关开也 hold/suppress
    from ..config import get_brain_config
    r = evaluate_gate_probe(sample_candidate(value=0.9), life, chat_busy=True)
    _check("chat_busy→不允许发送", r["gate"].get("allowed") is False,
           str(r["gate"].get("interruption_risk")))


def test_judge_schema_with_mock():
    print("\n[5] BrainJudge schema 校验（mock_response 绕过 LLM）")
    ctx = build_life_test_context(mode=REACTIVE, tick_type="")
    mock = json.dumps({
        "thought_summary": "ok", "next_action": "recall_memory",
        "focus": "x", "confidence": 0.6, "action_args": {"query": "q"},
    }, ensure_ascii=False)
    res = test_judge_decision(ctx, mock_response=mock)
    _check("ok", res["ok"], res.get("error"))
    _check("schema_valid", res["schema_valid"] is True, str(res["schema_valid"]))
    _check("decision.next_action", res["decision"]["next_action"] == "recall_memory")


def test_judge_invalid_action_fallback():
    print("\n[6] Judge 非法 next_action → 降级（不执行未知动作）")
    ctx = build_life_test_context(mode=REACTIVE, tick_type="")
    mock = json.dumps({"thought_summary": "bad", "next_action": "explode_things",
                       "confidence": 0.5}, ensure_ascii=False)
    res = test_judge_decision(ctx, mock_response=mock)
    _check("schema_invalid", res["schema_valid"] is False)
    # judge 把非法 action 降级为 abort
    _check("降级 abort", res["decision"]["next_action"] == "abort",
           res["decision"]["next_action"])


def test_snapshot():
    print("\n[7] snapshot_life_debug_state")
    snap = snapshot_life_debug_state()
    _check("ok", snap["ok"], snap.get("error"))
    _check("life_state 存在", "life_loop_status" in snap.get("life_state", {}))
    _check("config 存在", "life_loop_enabled" in snap.get("config", {}))


def main() -> int:
    print("=" * 60)
    print("main_brain 最小集成测试（mock，无真实 LLM）")
    print("=" * 60)
    test_reactive_session_routing()
    test_life_tick_dry_run()
    test_activity_selection()
    test_gate_hold_and_send()
    test_judge_schema_with_mock()
    test_judge_invalid_action_fallback()
    test_snapshot()
    print("\n" + "=" * 60)
    print(f"结果：{_passed} 通过 / {_failed} 失败")
    print("=" * 60)
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
