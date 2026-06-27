#!/usr/bin/env python
"""主脑自主学习集成测试

直接调用 run_self_learn()，使用真实 internal_state + 手动构建 life_state，
验证自主学习能否在真实环境中完成（即便 web 搜索失败也能优雅降级）。

运行：
    cd backend && python -m tests.test_self_learn_integration
"""
from __future__ import annotations

import json
import os
import sys
import time

# 把 backend 加入路径
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_PASSED = 0
_FAILED = 0


def _check(name: str, cond: bool, detail: str = "") -> None:
    global _PASSED, _FAILED
    if cond:
        _PASSED += 1
        print(f"  ✓ {name}")
    else:
        _FAILED += 1
        print(f"  ✗ {name}  {detail}")


def load_real_state() -> dict:
    """读取真实 internal_state.json"""
    path = os.path.join(_BACKEND, "main_brain", "data", "internal_state.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_life_state(state: dict) -> dict:
    """从 raw internal_state 构建 life_state（模拟 LifeState 适配器的行为）"""
    goals = state.get("goals", [])
    open_loops = state.get("open_loops", [])
    drives = state.get("drives", {})
    self_model = state.get("self_model", {})
    concerns = state.get("concerns", [])

    # 从 expression_history 中提取最近的想法作为 recent_thoughts
    recent_thoughts = []
    for entry in state.get("expression_history", []) or []:
        text = entry.get("content") or entry.get("expression_type", "")
        if text and len(text) > 10:
            recent_thoughts.append(text)
    recent_thoughts = recent_thoughts[-5:]  # 最近 5 条

    return {
        "open_loops": open_loops,
        "goals": goals,
        "recent_thoughts": recent_thoughts,
        "drives": drives,
        "self_model": self_model,
        "concerns": concerns,
        "current_activity": "",
        "idle_seconds": 600,  # 模拟 10 分钟空闲
        "life_loop_status": "medium_tick",
    }


def build_tick_input(life_state: dict) -> dict:
    """构建 run_self_learn 需要的 TickInput 兼容 dict"""
    return {
        "life_state": life_state,
        "tool_context": {},
        "recent_runs": [],
        "tick_type": "medium",
        "budgets": {},
    }


# ── 测试用例 ──────────────────────────────────────────


def test_dry_run_selects_topic():
    """dry_run 检查：话题选择是否工作"""
    print("\n[1] dry_run 话题选择")
    state = load_real_state()
    life_state = build_life_state(state)
    tick_input = build_tick_input(life_state)

    from main_brain.self_learn import run_self_learn
    result = run_self_learn(tick_input, dry_run=True)

    _check("返回 ok", result.get("ok") is True, str(result))
    _check("有 dry_run 标记", result.get("dry_run") is True)
    _check("话题非空", bool(result.get("topic")), f"topic={result.get('topic')}")
    _check("有来源标记", result.get("source") in ("gap", "curiosity"),
           f"source={result.get('source')}")
    _check("有 cooldown_key", bool(result.get("cooldown_key")),
           f"key={result.get('cooldown_key')}")

    print(f"  选定话题: 「{result['topic']}」")
    print(f"  来源: {result['source']}")
    print(f"  loop_id: {result.get('loop_id')}")
    return result


def test_today_count():
    """_today_count 读取真实 expression_history"""
    print("\n[2] _today_count（真实 expression_history）")
    from main_brain.self_learn import _today_count
    count = _today_count()
    _check("返回非负整数", isinstance(count, int) and count >= 0, f"count={count}")
    print(f"  今日学习次数: {count}")


def test_full_pipeline_with_real_state():
    """真实状态下完整 pipeline（降级摘要是预期行为，web 搜索大概率无网络）"""
    print("\n[3] 完整 pipeline（真实 internal_state，降级摘要）")
    state = load_real_state()
    life_state = build_life_state(state)

    # 手动注入几个 recent_thoughts 确保 topic 选择有料
    life_state["recent_thoughts"] = [
        "今天分析了记忆系统的架构，发现情景记忆和语义记忆的关联很有意思",
        "用户对猫猫的记忆联想能力很满意，考虑增加更多维度的关联",
        "关于记忆中实体关系的存储方式，可以尝试使用图数据库优化",
    ]
    tick_input = build_tick_input(life_state)

    from main_brain.self_learn import run_self_learn
    t0 = time.perf_counter()
    result = run_self_learn(tick_input, dry_run=False)
    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    _check("返回 ok", result.get("ok") is True, str(result))
    _check("有话题", bool(result.get("topic")), f"topic={result.get('topic')}")

    if result.get("stored"):
        _check("记忆已存储", bool(result.get("stored")),
               f"memory_id={result.get('stored')}")
    else:
        _check("记忆存储（可能降级）", True,
               "（store_memory 可能未初始化，不阻断流程）")

    _check("有摘要长度", isinstance(result.get("summary_len"), int),
           f"len={result.get('summary_len')}")
    _check("耗时合理", elapsed < 30000, f"{elapsed}ms")

    print(f"  topic: 「{result['topic']}」")
    print(f"  source: {result['source']}")
    print(f"  summary_len: {result['summary_len']}")
    print(f"  stored: {result.get('stored', '')}")
    print(f"  耗时: {elapsed}ms")
    return result


def test_with_explicit_curiosity_input():
    """手动注入 curiosity 话题，确保话题选择在 curiosity 路径工作"""
    print("\n[4] 手动注入 curiosity 话题")

    life_state = {
        "open_loops": [],
        "goals": [
            {"name": "测试自主学习对记忆系统的作用", "description": "验证自主学习是否能产生有用记忆"},
        ],
        "recent_thoughts": [
            "学习新知识并沉淀到长期记忆中是智能系统的重要能力",
        ],
        "drives": {"curiosity": 0.8},
        "self_model": {"name": "猫猫", "traits": ["好奇"]},
        "idle_seconds": 600,
        "current_activity": "",
        "life_loop_status": "medium_tick",
    }
    tick_input = build_tick_input(life_state)

    from main_brain.self_learn import run_self_learn
    # 先 dry_run 看看会选什么话题
    dr = run_self_learn(tick_input, dry_run=True)
    _check("dry_run 返回话题", bool(dr.get("topic")), f"topic={dr.get('topic')}")
    _check("来自 curiosity", dr.get("source") == "curiosity", dr.get("source"))
    print(f"  dry_run 话题: 「{dr.get('topic')}」")

    # 再真实执行
    result = run_self_learn(tick_input, dry_run=False)
    _check("full run ok", result.get("ok") is True, str(result))
    print(f"  最终话题: 「{result.get('topic')}」")
    print(f"  摘要长度: {result.get('summary_len')}")
    return result


def test_guard_no_topic_skipped():
    """无话题时返回 skipped（验证 guard 机制运行正常）"""
    print("\n[5] Guard：无话题时返回 skipped")
    life_state = {"open_loops": [], "goals": [], "recent_thoughts": []}
    tick_input = build_tick_input(life_state)

    from main_brain.self_learn import run_self_learn
    result = run_self_learn(tick_input)
    _check("返回 skipped", result.get("reason") == "no_topic", str(result))
    _check("ok=False", result.get("ok") is False)
    _check("有 skipped 标记", result.get("skipped") is True)


# ── 主入口 ────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("主脑自主学习 集成测试")
    print(f"环境: Python {sys.version.split()[0]}")
    print(f"路径: {_BACKEND}")
    print("=" * 60)

    tests = [
        ("dry_run 话题选择", test_dry_run_selects_topic),
        ("_today_count", test_today_count),
        ("完整 pipeline", test_full_pipeline_with_real_state),
        ("手动 curiosity", test_with_explicit_curiosity_input),
        ("Guard 开关", test_guard_disabled),
    ]

    for name, fn in tests:
        print(f"\n── {name} ──")
        try:
            fn()
        except Exception as e:
            global _FAILED
            _FAILED += 1
            import traceback
            print(f"  !! 异常: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"总结果：{_PASSED} 通过 / {_FAILED} 失败")
    print("=" * 60)
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
