#!/usr/bin/env python3
"""LLM-based causal extraction for the world-model demo.

The writer turns a single BrainRun record into a structured causal packet:
event summary + causal relations + short forecast.
It only uses observable fields from the run log and falls back to heuristics
when the LLM is unavailable or returns malformed JSON.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from itertools import pairwise
from typing import Any


logger = logging.getLogger("world_model_demo.causal_writer")

ALLOWED_RELATION_TYPES = {
    "causal",
    "temporal",
    "conditional",
    "enables",
    "blocks",
    "associated",
}

CAUSAL_SYSTEM_PROMPT = """你是 AiBrain 的因果写入器。
你的任务是把一次 BrainRun 转成结构化因果数据，用于后续写入本地因果库。

严格规则：
1. 只能使用输入 JSON 中的可观测字段，不要使用隐藏思维链或臆测内容。
2. 不要编造不存在的事实；证据不足时使用 associated，并降低 confidence。
3. 只输出严格 JSON，不要输出解释、markdown 或代码块。
4. relations 最多 5 条，尽量短、具体、可验证。
5. relation_type 只能从以下值中选择：
   causal / temporal / conditional / enables / blocks / associated

输出格式：
{
  "event": {
    "summary": "一句话总结这个 run 的可观测事件",
    "state": {
      "mode": "background",
      "selected_activity": "reflect",
      "tick_type": "medium_tick",
      "stop_reason": "max_cycles"
    }
  },
  "relations": [
    {
      "cause": "cause phrase",
      "effect": "effect phrase",
      "relation_type": "causal",
      "confidence": 0.82,
      "evidence": "short evidence"
    }
  ],
  "forecast": {
    "summary": "short next-step forecast",
    "confidence": 0.63
  }
}"""


def build_causal_packet(run: dict, history: list[dict] | None = None, *, timeout: int = 15) -> dict:
    """Extract a causal packet from a BrainRun.

    The LLM path is preferred. When it fails, a deterministic heuristic packet
    is returned so the demo remains usable offline.
    """
    history = history or []
    prompt_payload = _build_prompt_payload(run, history)

    try:
        from modules.brain.llm import call_llm

        raw = call_llm(
            CAUSAL_SYSTEM_PROMPT,
            json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            timeout=timeout,
            max_tokens=1600,
        )
        parsed = _parse_json_response(raw)
        packet = _normalize_packet(parsed, run)
        packet["writer"] = "llm"
        packet["llm_used"] = True
        packet["raw_preview"] = raw[:240]
        if not packet["relations"]:
            fallback = _fallback_packet(run, history)
            fallback["writer"] = "fallback"
            fallback["llm_used"] = True
            fallback["llm_preview"] = raw[:120]
            return fallback
        return packet
    except Exception as exc:  # noqa: BLE001 - demo should keep going
        logger.warning("[causal_writer] LLM extraction failed: %s", exc)
        packet = _fallback_packet(run, history)
        packet["writer"] = "fallback"
        packet["llm_used"] = False
        packet["error"] = f"{exc.__class__.__name__}: {exc}"
        return packet


def _build_prompt_payload(run: dict, history: list[dict]) -> dict:
    return {
        "run": _compact_run(run),
        "history": [_compact_history_item(item) for item in history[-2:]],
    }


def _compact_run(run: dict) -> dict:
    cycles = []
    for cycle in (run.get("cycles") or [])[:6]:
        if not isinstance(cycle, dict):
            continue
        cycles.append(
            {
                "cycle_index": cycle.get("cycle_index"),
                "action": cycle.get("action", ""),
                "focus": _trim(cycle.get("focus", ""), 80),
                "result_summary": _trim(cycle.get("result_summary", ""), 120),
                "reply_ready": bool(cycle.get("reply_ready")),
                "confidence": _to_float(cycle.get("confidence", 0.0)),
                "error": _trim(cycle.get("error", ""), 120),
            }
        )

    return {
        "run_id": run.get("run_id", ""),
        "mode": run.get("mode", ""),
        "selected_activity": run.get("selected_activity", ""),
        "stop_reason": run.get("stop_reason", ""),
        "trigger": {
            "tick_type": (run.get("trigger") or {}).get("tick_type", ""),
        },
        "actions": [str(a) for a in (run.get("actions") or []) if a],
        "cycles": cycles,
        "tool_results": [_compact_tool_result(item) for item in (run.get("tool_results") or [])[:6]],
        "state_deltas": [_compact_state_delta(item) for item in (run.get("state_deltas") or [])[:6]],
        "memory_context_count": run.get("memory_context_count", 0),
    }


def _compact_history_item(run: dict) -> dict:
    return {
        "run_id": run.get("run_id", ""),
        "mode": run.get("mode", ""),
        "selected_activity": run.get("selected_activity", ""),
        "stop_reason": run.get("stop_reason", ""),
        "tick_type": (run.get("trigger") or {}).get("tick_type", ""),
        "actions": [str(a) for a in (run.get("actions") or []) if a][:4],
        "cycle_count": run.get("cycle_count", len(run.get("cycles") or [])),
    }


def _compact_tool_result(item: dict) -> dict:
    if not isinstance(item, dict):
        return {"name": "", "status": "unknown", "result": ""}
    return {
        "name": item.get("name", item.get("tool", "")),
        "status": "error" if item.get("error") else "ok",
        "result": _trim(item.get("result", item.get("output", "")), 120),
        "error": _trim(item.get("error", ""), 120),
    }


def _compact_state_delta(item: dict) -> dict:
    if not isinstance(item, dict):
        return {"field": "", "from": "", "to": ""}
    return {
        "field": item.get("field", item.get("key", "")),
        "from": _trim(item.get("from", ""), 80),
        "to": _trim(item.get("to", ""), 80),
    }


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    for candidate in (
        raw,
        _extract_code_block(raw),
        _extract_first_object(raw),
    ):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    logger.warning("[causal_writer] JSON parse failed, falling back")
    return {}


def _extract_code_block(raw: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_first_object(raw: str) -> str:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0).strip() if match else ""


def _normalize_packet(packet: dict, run: dict) -> dict:
    event = packet.get("event") if isinstance(packet, dict) else {}
    if not isinstance(event, dict):
        event = {}
    relations = packet.get("relations") if isinstance(packet, dict) else []
    if not isinstance(relations, list):
        relations = []
    forecast = packet.get("forecast") if isinstance(packet, dict) else {}
    if not isinstance(forecast, dict):
        forecast = {}

    normalized_relations = []
    for rel in relations[:5]:
        normalized = _normalize_relation(rel)
        if normalized:
            normalized_relations.append(normalized)

    if not normalized_relations:
        normalized_relations = _fallback_relations(run)

    event_summary = _trim(event.get("summary", ""), 240)
    if not event_summary:
        event_summary = _default_event_summary(run)

    state = event.get("state") if isinstance(event.get("state"), dict) else {}
    if not state:
        state = _default_state(run)

    forecast_summary = _trim(forecast.get("summary", ""), 200)
    if not forecast_summary:
        forecast_summary = _default_forecast(run, normalized_relations)

    forecast_confidence = _clamp01(forecast.get("confidence", 0.55))
    if forecast_confidence <= 0.0:
        forecast_confidence = _default_forecast_confidence(run, normalized_relations)

    return {
        "event": {
            "summary": event_summary,
            "state": state,
        },
        "relations": normalized_relations,
        "forecast": {
            "summary": forecast_summary,
            "confidence": round(forecast_confidence, 3),
        },
    }


def _normalize_relation(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    cause = _trim(item.get("cause", item.get("source", item.get("from", ""))), 120)
    effect = _trim(item.get("effect", item.get("target", item.get("to", ""))), 120)
    relation_type = str(item.get("relation_type", item.get("relation", "associated"))).strip().lower()
    if relation_type not in ALLOWED_RELATION_TYPES:
        relation_type = "associated"
    confidence = _clamp01(item.get("confidence", 0.5))
    evidence = _trim(item.get("evidence", item.get("reason", "")), 240)
    if not cause or not effect or cause == effect:
        return None
    return {
        "cause": cause,
        "effect": effect,
        "relation_type": relation_type,
        "confidence": round(confidence, 3),
        "evidence": evidence,
    }


def _fallback_packet(run: dict, history: list[dict]) -> dict:
    relations = _fallback_relations(run)
    return {
        "event": {
            "summary": _default_event_summary(run),
            "state": _default_state(run),
        },
        "relations": relations,
        "forecast": {
            "summary": _default_forecast(run, relations),
            "confidence": round(_default_forecast_confidence(run, relations), 3),
        },
    }


def _fallback_relations(run: dict) -> list[dict]:
    actions = [str(a) for a in (run.get("actions") or []) if a]
    if not actions:
        cycles = run.get("cycles") or []
        for cycle in cycles:
            if isinstance(cycle, dict):
                action = str(cycle.get("action", "")).strip()
                if action:
                    actions.append(action)

    selected_activity = str(run.get("selected_activity", "")).strip() or "unknown"
    stop_reason = str(run.get("stop_reason", "")).strip() or "unknown"
    tick_type = str((run.get("trigger") or {}).get("tick_type", "")).strip() or "unknown"
    repeated_action = _most_common(actions)
    relations: list[dict] = []

    if actions:
        for left, right in pairwise(actions[:4]):
            relations.append(
                {
                    "cause": f"action:{left}",
                    "effect": f"next_action:{right}",
                    "relation_type": "temporal",
                    "confidence": 0.55,
                    "evidence": "Observed action order in cycle sequence.",
                }
            )

    relations.append(
        {
            "cause": f"tick_type:{tick_type}",
            "effect": f"selected_activity:{selected_activity}",
            "relation_type": "conditional",
            "confidence": 0.58,
            "evidence": "Selected activity is chosen under this tick context.",
        }
    )

    if stop_reason == "max_cycles" and repeated_action:
        relations.append(
            {
                "cause": f"repeated_action:{repeated_action}",
                "effect": "stop_reason:max_cycles",
                "relation_type": "causal",
                "confidence": 0.7,
                "evidence": "Repeated actions preceded a max_cycles stop in this run.",
            }
        )
    elif stop_reason in {"ready", "completed"} and actions:
        relations.append(
            {
                "cause": f"final_action:{actions[-1]}",
                "effect": f"stop_reason:{stop_reason}",
                "relation_type": "causal",
                "confidence": 0.72,
                "evidence": "Final action aligns with a successful completion signal.",
            }
        )
    elif stop_reason in {"sleep", "timeout", "abort"} and actions:
        relations.append(
            {
                "cause": f"run_pressure:{stop_reason}",
                "effect": f"selected_activity:{selected_activity}",
                "relation_type": "blocks",
                "confidence": 0.55,
                "evidence": "The run ended early or was interrupted.",
            }
        )

    if len(relations) > 5:
        relations = relations[:5]
    return relations


def _default_event_summary(run: dict) -> str:
    actions = [str(a) for a in (run.get("actions") or []) if a]
    cycle_count = run.get("cycle_count", len(run.get("cycles") or []))
    mode = run.get("mode", "")
    activity = run.get("selected_activity", "")
    stop_reason = run.get("stop_reason", "")
    tick_type = (run.get("trigger") or {}).get("tick_type", "")
    action_text = " -> ".join(actions[:4]) if actions else "no explicit actions"
    return (
        f"{mode} run on {tick_type} executed {cycle_count} cycles with {activity}, "
        f"ended by {stop_reason}; actions: {action_text}"
    )


def _default_state(run: dict) -> dict:
    return {
        "mode": run.get("mode", ""),
        "selected_activity": run.get("selected_activity", ""),
        "tick_type": (run.get("trigger") or {}).get("tick_type", ""),
        "stop_reason": run.get("stop_reason", ""),
    }


def _default_forecast(run: dict, relations: list[dict]) -> str:
    actions = [str(a) for a in (run.get("actions") or []) if a]
    selected_activity = run.get("selected_activity", "") or "reflect"
    stop_reason = run.get("stop_reason", "")
    if stop_reason == "max_cycles":
        if actions and actions[-1] == "recall_memory":
            return "The next run will likely repeat recall_memory or switch to create_pending."
        return f"The next run will likely continue {selected_activity} with another short retrieval step."
    if stop_reason in {"ready", "completed"}:
        return "The next step will likely shift toward reply or cleanup because the run completed."
    if relations:
        return f"The next step will likely follow the same pattern around {selected_activity}."
    return "The next step is uncertain; gather more evidence before making a stronger claim."


def _default_forecast_confidence(run: dict, relations: list[dict]) -> float:
    stop_reason = run.get("stop_reason", "")
    if stop_reason == "max_cycles":
        return 0.68
    if stop_reason in {"ready", "completed"}:
        return 0.72
    return 0.55 if relations else 0.45


def _most_common(items: list[str]) -> str:
    if not items:
        return ""
    counter = Counter(items)
    return counter.most_common(1)[0][0]


def _trim(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: Any, default: float = 0.0) -> float:
    number = _to_float(value, default)
    return max(0.0, min(1.0, number))
