"""运行轨迹采集器（T003）

从 brain_runs.jsonl 中读取运行摘要和完整轨迹，归一化为 ProcedureExample。

采集策略：
  - 只采集有 cycles 且 stop_reason 为 ready/completed 的成功运行
  - 跳过 wait/sleep 的纯空闲运行
  - 支持按窗口大小采集最近 N 条运行
"""

import json
import logging
import os
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureExample
from main_brain.logging.event_log import get_event_log, _LOG_PATH

logger = logging.getLogger("main_brain.procedural.collector")

# 默认采集窗口
_DEFAULT_WINDOW = 50

# 跳过的不产生样本的动作
_SKIP_ACTIONS = {"wait", "sleep", "abort"}


def collect_procedure_examples(
    window: int = _DEFAULT_WINDOW,
    *,
    modes: Optional[list[str]] = None,
    min_cycles: int = 1,
    after_run_id: str = "",
) -> list[ProcedureExample]:
    """从 brain_runs.jsonl 采集程序记忆样本。

    Args:
        window: 从最新运行倒序读取的最大条数。
        modes: 过滤运行模式，如 ["background"] 只采后台。None 表示全部。
        min_cycles: 最少 cycle 数，跳过太短的运行。
        after_run_id: 只采集该 run_id 之后的新运行；为空时采集窗口内全部运行。

    Returns:
        ProcedureExample 列表。
    """
    examples: list[ProcedureExample] = []
    runs = _fetch_recent_runs(window, after_run_id=after_run_id)

    for run in runs:

        # 模式过滤
        if modes and run.get("mode") not in modes:
            continue

        # 跳过没有完整轨迹的记录
        if not run.get("cycles"):
            continue

        # 跳过纯空闲运行
        actions = [c.get("action", "") for c in run.get("cycles", [])]
        if all(a in _SKIP_ACTIONS for a in actions):
            continue

        # 检查最小 cycle 数
        if len(run.get("cycles", [])) < min_cycles:
            continue

        ex = _build_example(run)
        if ex:
            examples.append(ex)

    logger.info(
        "[procedural.collector] collected %d examples from last %d runs (after_run_id=%s)",
        len(examples), window, after_run_id or "-",
    )
    return examples


def _fetch_recent_runs(window: int, *, after_run_id: str = "") -> list[dict]:
    """从 event_log 读取最近运行。

    优先从 JSONL 尾部读取完整轨迹（含 cycles），
    如果 ring buffer 中有完整摘要则补充。
    """
    runs = []
    collected = 0

    if not os.path.isfile(_LOG_PATH):
        return runs

    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 从尾部倒序遍历，收集最近的 runs
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # 只关注 run 记录（有 run_id 和 mode）
            if not rec.get("run_id") or not rec.get("mode"):
                continue

            runs.append(rec)
            collected += 1
            if collected >= window:
                break

    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[procedural.collector] failed to read brain_runs.jsonl: %s", e)

    # 倒序 -> 正序（从旧到新）
    runs.reverse()

    if after_run_id:
        found = False
        filtered: list[dict] = []
        for run in runs:
            if not found:
                if run.get("run_id") == after_run_id:
                    found = True
                continue
            filtered.append(run)
        if found:
            runs = filtered
        else:
            logger.info(
                "[procedural.collector] checkpoint %s not found in window=%d; collecting full window",
                after_run_id, window,
            )
    return runs


def _build_example(run: dict) -> Optional[ProcedureExample]:
    """将一条运行记录归一化为样本。"""
    run_id = run.get("run_id", "")
    if not run_id:
        return None

    cycles = run.get("cycles", [])
    if not cycles:
        return None

    # 跳过纯 wait/sleep 的空闲运行
    actions = [c.get("action", "") for c in cycles]
    if all(a in _SKIP_ACTIONS for a in actions):
        return None

    # 确定结果
    stop_reason = run.get("stop_reason", "")
    outcome, reward = _classify_outcome(stop_reason)

    # 构建上下文摘要
    context_digest = {
        "activity": run.get("selected_activity", ""),
        "stop_reason": stop_reason,
        "cycle_count": len(cycles),
        "trigger": run.get("trigger", {}),
        "actions": [c.get("action", "") for c in cycles],
    }

    # 构建动作序列（带摘要，不含完整思维链）
    action_sequence = []
    for c in cycles:
        action_sequence.append({
            "action": c.get("action", ""),
            "focus": c.get("focus", ""),
            "confidence": c.get("confidence", 0.0),
            "has_args": bool(c.get("action_args")),
        })

    # 工具调用摘要
    tool_calls = _extract_tool_calls(run.get("tool_results", []))

    # 状态变化摘要
    state_deltas = _extract_state_deltas(run.get("state_deltas", []))

    example_id = f"pex_{run_id}"

    return ProcedureExample(
        example_id=example_id,
        run_id=run_id,
        mode=run.get("mode", ""),
        tick_type=run.get("trigger", {}).get("tick_type", ""),
        context_digest=context_digest,
        action_sequence=action_sequence,
        tool_calls=tool_calls,
        state_deltas=state_deltas,
        outcome=outcome,
        reward=reward,
        source_refs=[f"brain_runs:{run_id}"],
    )


def _classify_outcome(stop_reason: str):
    """根据 stop_reason 判定结果和奖励值。"""
    success_reasons = {"ready", "completed"}
    partial_reasons = {"sleep", "max_cycles"}
    if stop_reason in success_reasons:
        return "success", 1.0
    elif stop_reason in partial_reasons:
        return "partial", 0.5
    elif stop_reason == "abort":
        return "fail", 0.0
    else:
        return "unknown", 0.3


def _extract_tool_calls(tool_results: list[dict]) -> list[dict]:
    """从 tool_results 提取工具调用摘要。"""
    calls = []
    for tr in tool_results[-10:]:  # 最多最近 10 条
        calls.append({
            "tool": tr.get("tool", tr.get("name", "")),
            "status": "success" if not tr.get("error") else "error",
            "duration_ms": tr.get("duration_ms", 0),
        })
    return calls


def _extract_state_deltas(state_deltas: list[dict]) -> list[dict]:
    """从 state_deltas 提取变化摘要。"""
    deltas = []
    for sd in state_deltas[-10:]:
        deltas.append({
            "field": sd.get("field", sd.get("key", "")),
            "from": sd.get("from", ""),
            "to": sd.get("to", ""),
        })
    return deltas
