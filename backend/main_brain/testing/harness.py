"""harness — 统一测试入口（T020）

probe 函数均支持 dry_run / mock，不依赖 Flask 路由，可直接 import 做模块化测试
（plan 第八节「测试与调试接口」验收要求）。

  test_judge_decision()       — judge 结构化输出 + schema 校验（mock_response 绕过 LLM）
  run_cycle_probe()           — 单轮/多轮 cycle runner 路由（mock_decision + 真 adapter / dry_run）
  select_activity_probe()     — ActivitySelector 选择
  evaluate_gate_probe()       — 表达闸门判定（不发送）
  build_life_test_context()   — 构造测试上下文（fixtures 转发）
  snapshot_life_debug_state() — LifeState / recent runs / pending / config 摘要
"""
from __future__ import annotations

from typing import Any

from ..controller import BrainCycleRunner
from ..contracts import BrainRunContext, ACTIONS
from ..judge import get_brain_judge
from ..activity_selector import get_activity_selector
from ..expression_gate import get_expression_gate
from ..adapters import build_action_handlers
from .mocks import MockJudge
from .fixtures import build_life_test_context
from .assertions import assert_decision_schema


def test_judge_decision(
    context: BrainRunContext,
    *,
    mock_response: str | None = None,
    validate_schema: bool = True,
) -> dict:
    """测试 BrainJudge 结构化输出，不执行任何副作用。

    mock_response 非空时绕过真实 LLM（稳定自动化测试）。
    Returns: {ok, decision, schema_valid, latency_ms, error}
    """
    import json as _json
    import time as _t
    t0 = _t.perf_counter()
    out: dict[str, Any] = {"ok": True, "decision": None, "schema_valid": False,
                           "latency_ms": 0.0, "error": ""}
    try:
        judge = get_brain_judge()
        jr = judge.decide(context.to_judge_view(), mode=context.run.mode,
                          activity=context.selected_activity, mock_response=mock_response)
        out["decision"] = jr.decision.to_dict()
        out["schema_valid"] = jr.schema_valid
        if jr.error:
            out["error"] = jr.error
        if validate_schema and mock_response is not None:
            # 用原始 mock 解析再校验一次 schema（独立于 judge 内部）
            try:
                parsed = _json.loads(mock_response) if mock_response.strip().startswith("{") else {}
            except Exception:
                parsed = {}
            ok, msg = assert_decision_schema(parsed or jr.decision.to_dict())
            out["schema_valid"] = out["schema_valid"] and ok
            if not ok:
                out["error"] = out["error"] or msg
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
    out["latency_ms"] = round((_t.perf_counter() - t0) * 1000.0, 1)
    return out


def run_cycle_probe(
    context: BrainRunContext,
    *,
    mock_decision: dict | None = None,
    mock_decisions: list[dict] | None = None,
    dry_run: bool = True,
    max_cycles: int = 3,
) -> dict:
    """测试 cycle runner：验证 next_action 路由 / state delta / 错误写入。

    mock_decisions 提供多轮序列；mock_decision 提供单个固定决策。
    dry_run=True 不写状态、不调真实工具。
    Returns: {ok, stop_reason, cycle_count, actions, errors}
    """
    out: dict[str, Any] = {"ok": True, "stop_reason": "", "cycle_count": 0,
                           "actions": [], "errors": []}
    try:
        if mock_decisions:
            judge = MockJudge(raw_dicts=mock_decisions)
        else:
            judge = MockJudge(raw_dicts=[mock_decision or {"next_action": "sleep"}])
        runner = BrainCycleRunner(judge, build_action_handlers())
        stop = runner.run(context, max_cycles=max_cycles, timeout_seconds=15,
                          dry_run=dry_run, mock_judge=judge)
        out["stop_reason"] = stop
        out["cycle_count"] = len(context.run.cycles)
        out["actions"] = [c.action for c in context.run.cycles]
        out["errors"] = [c.error for c in context.run.cycles if c.error]
        out["cycles"] = [c.to_dict() for c in context.run.cycles]
    except Exception as e:
        out["ok"] = False
        out["stop_reason"] = "error"
        out["errors"].append(str(e))
    return out


def select_activity_probe(
    life_state: dict,
    tick_type: str = "medium_tick",
    *,
    recent_runs: list[dict] | None = None,
    pending_expressions: list[dict] | None = None,
    autonomy_level: str = "assist",
) -> dict:
    """测试 ActivitySelector 选择。Returns: {ok, selected_activity, reason}。"""
    try:
        activity, reason = get_activity_selector().select(
            life_state, tick_type,
            recent_runs=recent_runs,
            pending_expressions=pending_expressions,
            autonomy_level=autonomy_level,
        )
        return {"ok": True, "selected_activity": activity, "reason": reason}
    except Exception as e:
        return {"ok": False, "selected_activity": "", "reason": str(e)}


def evaluate_gate_probe(
    candidate: dict,
    life_state: dict,
    *,
    recent_messages: list[dict] | None = None,
    chat_busy: bool = False,
) -> dict:
    """测试主动联系闸门，不发送消息。Returns: {ok, gate}。"""
    try:
        result = get_expression_gate().evaluate(
            candidate, life_state,
            recent_messages=recent_messages, chat_busy=chat_busy)
        return {"ok": True, "gate": result.to_dict()}
    except Exception as e:
        return {"ok": False, "gate": {}, "error": str(e)}


def snapshot_life_debug_state() -> dict:
    """返回测试视角的 LifeState / recent runs / pending / config 摘要。

    可被后端测试、脚本、临时 CLI 复用（plan snapshot_life_debug_state）。
    """
    try:
        from ..adapters.state import get_state_adapter
        from ..logging.event_log import get_event_log
        from ..config import get_brain_config
        life = get_state_adapter().read_life_state()
        cfg = get_brain_config()
        return {
            "ok": True,
            "life_state": life,
            "recent_runs": get_event_log().recent_runs(limit=10),
            "pending_expressions": life.get("pending_expressions", []),
            "config": {
                "life_loop_enabled": cfg.life_loop_enabled,
                "proactive_contact_enabled": cfg.proactive_enabled,
                "autonomy_level": cfg.autonomy_level,
                "brain_session_enabled": cfg.session_enabled,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    "test_judge_decision", "run_cycle_probe", "select_activity_probe",
    "evaluate_gate_probe", "build_life_test_context", "snapshot_life_debug_state",
]
