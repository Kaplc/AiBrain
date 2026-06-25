#!/usr/bin/env python3
"""World model demo for AiBrain.

This script stitches together existing backend layers into one short-horizon
prediction probe:
  - brain_runs.jsonl event log
  - procedural memory collection / mining / matching
  - semantic memory search
  - entity graph expansion
  - scene graph / scene diffusion

It is intentionally lightweight. The goal is to validate whether the current
backend can already support a structured world model, and the demo now also
includes an LLM-first causal write path that incrementally persists extracted
events and relations for later reuse.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

for path in (BACKEND, ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


COMPONENT_SPECS: dict[str, tuple[str, str]] = {
    "get_event_log": ("main_brain.logging.event_log", "get_event_log"),
    "collect_procedure_examples": (
        "main_brain.procedural_memory.collector",
        "collect_procedure_examples",
    ),
    "mine_procedure_templates": (
        "main_brain.procedural_memory.miner",
        "mine_procedure_templates",
    ),
    "enrich_tick_context_with_procedures": (
        "main_brain.procedural_memory.policy",
        "enrich_tick_context_with_procedures",
    ),
    "get_procedure_store": (
        "main_brain.memory.procedural.store",
        "get_procedure_store",
    ),
    "get_state_summary": (
        "main_brain.procedural_memory.trace",
        "get_state_summary",
    ),
    "search_memory": ("main_brain.memory.core", "search_memory"),
    "get_graph": ("modules.brain.graph", "get_graph"),
    "get_scene_graph": ("main_brain.memory.scene_graph", "get_scene_graph"),
    "get_scene_diffusion": (
        "main_brain.memory.scene_diffusion",
        "get_scene_diffusion",
    ),
    "get_causal_store": ("causal_store", "get_causal_store"),
    "sync_recent_runs": ("causal_store", "sync_recent_runs"),
}


def load_components() -> tuple[dict[str, Any], dict[str, str]]:
    """Import backend components lazily so one broken dependency does not kill the demo."""
    components: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, (module_name, attr_name) in COMPONENT_SPECS.items():
        try:
            module = importlib.import_module(module_name)
            components[name] = getattr(module, attr_name)
        except Exception as exc:  # noqa: BLE001 - demo should keep going
            components[name] = None
            errors[name] = f"{exc.__class__.__name__}: {exc}"
    return components, errors


COMPONENTS, IMPORT_ERRORS = load_components()


def _component(name: str):
    value = COMPONENTS.get(name)
    if value is None:
        raise RuntimeError(IMPORT_ERRORS.get(name, f"{name} is unavailable"))
    return value


def _safe_call(fn, *args, default=None, **kwargs):
    if fn is None:
        return default
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 - demo should collect partial output
        return default


def _read_recent_run_records(log_path: Path, limit: int) -> list[dict]:
    """Read the newest run records from the JSONL event log.

    The log file mixes run records and event records. We keep only entries that
    look like run summaries.
    """
    if not log_path.is_file():
        return []

    records: list[dict] = []
    try:
        with log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("run_id") and rec.get("mode"):
                records.append(rec)
                if len(records) >= limit:
                    break
    except OSError:
        return []

    records.reverse()
    return records


def _fallback_run() -> dict:
    return {
        "run_id": "fallback",
        "mode": "background",
        "trigger": {"tick_type": "medium_tick"},
        "selected_activity": "reflect",
        "actions": ["recall_memory", "update_state", "final_reply"],
        "stop_reason": "unknown",
        "cycles": [],
        "pending_created": [],
        "state_deltas": [],
        "tool_results": [],
    }


def _latest_run(event_log, recent_limit: int, run_id: str | None) -> tuple[dict, list[dict], str]:
    """Return the latest usable run and a small history window."""
    log_path = Path(event_log.log_path()) if event_log else BACKEND / "logs" / "main_brain" / "brain_runs.jsonl"
    recent_runs = _read_recent_run_records(log_path, recent_limit)

    if run_id:
        if event_log is not None:
            run = _safe_call(event_log.get_run, run_id, default=None)
            if run:
                return run, recent_runs, "event_log.get_run"
        for rec in reversed(recent_runs):
            if rec.get("run_id") == run_id:
                return rec, recent_runs, "recent_records"
        return _fallback_run(), recent_runs, "fallback"

    if recent_runs:
        return recent_runs[-1], recent_runs, "recent_records"

    return _fallback_run(), recent_runs, "fallback"


def _normalize_actions(run: dict) -> list[str]:
    actions = list(run.get("actions") or [])
    if actions:
        return [str(a) for a in actions if a]
    cycles = run.get("cycles") or []
    out = []
    for cycle in cycles:
        if isinstance(cycle, dict):
            action = str(cycle.get("action", "")).strip()
            if action:
                out.append(action)
    return out


def _summarize_run(run: dict) -> dict:
    trigger = run.get("trigger") or {}
    actions = _normalize_actions(run)
    cycles = run.get("cycles") or []
    last_error = run.get("last_error", "")
    if not last_error and cycles:
        last_cycle = cycles[-1]
        if isinstance(last_cycle, dict):
            last_error = str(last_cycle.get("error", "") or "")

    return {
        "run_id": run.get("run_id", ""),
        "mode": run.get("mode", ""),
        "selected_activity": run.get("selected_activity", ""),
        "stop_reason": run.get("stop_reason", ""),
        "tick_type": trigger.get("tick_type", ""),
        "actions": actions,
        "cycle_count": run.get("cycle_count", len(cycles)),
        "last_error": last_error,
    }


def _build_run_context(run: dict) -> dict:
    summary = _summarize_run(run)
    pending_created = run.get("pending_created", []) or []
    goals = run.get("goals", []) or []

    return {
        "mode": summary["mode"],
        "tick_type": summary["tick_type"],
        "selected_activity": summary["selected_activity"],
        "activity": summary["selected_activity"] or summary["stop_reason"] or summary["mode"],
        "actions": summary["actions"],
        "open_loops": pending_created,
        "goals": goals,
        "life_state": {
            "open_loops": pending_created,
            "goals": goals,
            "selected_activity": summary["selected_activity"],
        },
        "trigger": run.get("trigger", {}),
    }


def _build_primary_query(args: argparse.Namespace, run: dict) -> str:
    if args.query:
        return args.query

    base = run.get("selected_activity") or run.get("stop_reason") or run.get("mode") or "world model"
    tick_type = (run.get("trigger") or {}).get("tick_type", "")
    return " ".join(part for part in [base, "世界模型", "后果", "预测", tick_type] if part)


def _build_run_query(run: dict) -> str:
    summary = _summarize_run(run)
    parts = [
        summary["mode"],
        summary["selected_activity"],
        summary["stop_reason"],
        summary["tick_type"],
    ]
    parts.extend(summary["actions"][:4])
    return " ".join(part for part in parts if part) or "world model"


def _to_score(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: Any, default: float = 0.0) -> float:
    score = _to_score(value, default)
    return max(0.0, min(1.0, score))


def _merge_hits(collections: list[tuple[str, list[dict]]]) -> list[dict]:
    """Merge hits from multiple searches by id."""
    merged: dict[str, dict] = {}
    for source_name, hits in collections:
        for hit in hits or []:
            if not isinstance(hit, dict):
                continue
            hit_id = str(hit.get("id") or hit.get("mem0_id") or hit.get("scene_id") or "")
            if not hit_id:
                continue

            score = max(
                _to_score(hit.get("score"), 0.0),
                _to_score(hit.get("spread_score"), 0.0),
                _to_score(hit.get("activation"), 0.0),
                _to_score(hit.get("weight"), 0.0),
            )
            text = str(hit.get("text", "") or hit.get("memory", "") or "")
            entities = hit.get("entities") or []
            payload = hit.get("payload")

            entry = merged.get(hit_id)
            if entry is None:
                entry = {
                    "id": hit_id,
                    "text": text,
                    "score": score,
                    "sources": [source_name],
                    "entities": list(dict.fromkeys(str(e) for e in entities if e)),
                    "payload": payload,
                }
                if "trace" in hit:
                    entry["trace"] = hit["trace"]
                merged[hit_id] = entry
                continue

            entry["score"] = max(entry.get("score", 0.0), score)
            if source_name not in entry["sources"]:
                entry["sources"].append(source_name)
            if text and len(text) > len(entry.get("text", "")):
                entry["text"] = text
            merged_entities = set(entry.get("entities", []))
            merged_entities.update(str(e) for e in entities if e)
            entry["entities"] = sorted(merged_entities)
            if entry.get("payload") is None and payload is not None:
                entry["payload"] = payload
            if "trace" in hit and "trace" not in entry:
                entry["trace"] = hit["trace"]

    merged_hits = list(merged.values())
    merged_hits.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return merged_hits


def _collect_procedural_signals(run: dict, args: argparse.Namespace) -> dict:
    get_procedure_store = COMPONENTS.get("get_procedure_store")
    get_state_summary = COMPONENTS.get("get_state_summary")
    collect_procedure_examples = COMPONENTS.get("collect_procedure_examples")
    mine_procedure_templates = COMPONENTS.get("mine_procedure_templates")
    enrich_tick_context_with_procedures = COMPONENTS.get("enrich_tick_context_with_procedures")

    store = _safe_call(get_procedure_store, default=None)
    state_summary = _safe_call(get_state_summary, default={})
    counts = _safe_call(store.get_counts, default={}) if store else {}
    examples = _safe_call(collect_procedure_examples, args.example_window, default=[], min_cycles=1) or []
    mined_templates = []
    if examples:
        mined = _safe_call(
            mine_procedure_templates,
            examples,
            default=[],
            min_support=args.mine_support,
            min_success_rate=args.mine_success_rate,
            existing_count=counts.get("total_raw", 0),
        ) or []
        mined_templates = [t.to_dict() if hasattr(t, "to_dict") else dict(t) for t in mined]

    context = _build_run_context(run)
    context = _safe_call(
        enrich_tick_context_with_procedures,
        context,
        default=context,
        top_k=args.procedure_top_k,
    ) or context

    return {
        "state_summary": state_summary,
        "counts": counts,
        "examples": [ex.to_dict() if hasattr(ex, "to_dict") else dict(ex) for ex in examples[: args.example_window]],
        "mined_templates": mined_templates[: args.procedure_top_k],
        "context": context,
        "procedure_matches": context.get("procedure_matches", [])[: args.procedure_top_k],
    }


def _collect_memory_signals(primary_query: str, run_query: str, args: argparse.Namespace) -> dict:
    search_memory = COMPONENTS.get("search_memory")
    import_error = IMPORT_ERRORS.get("search_memory")
    if search_memory is None:
        return {
            "primary_query": primary_query,
            "run_query": run_query,
            "hits": [],
            "error": import_error or "search_memory unavailable",
        }

    collections = []
    errors = []
    for source_name, query in [("memory:primary", primary_query), ("memory:run", run_query)]:
        try:
            hits = search_memory(query) or []
            collections.append((source_name, hits))
        except Exception as exc:  # noqa: BLE001 - partial results are still useful
            errors.append(f"{source_name}: {exc.__class__.__name__}: {exc}")
            collections.append((source_name, []))

    merged = _merge_hits(collections)
    return {
        "primary_query": primary_query,
        "run_query": run_query,
        "hits": merged[: args.memory_top_k],
        "errors": errors,
    }


def _fallback_entities(run: dict, primary_query: str) -> list[str]:
    candidates = [
        run.get("selected_activity", ""),
        run.get("stop_reason", ""),
        (run.get("trigger") or {}).get("tick_type", ""),
        "程序记忆",
        "世界模型",
        "记忆",
    ]
    if primary_query:
        candidates.append(primary_query)

    entities = []
    for candidate in candidates:
        text = str(candidate).strip()
        if text and text not in entities:
            entities.append(text)
    return entities


def _collect_graph_signals(run: dict, memory_hits: list[dict], primary_query: str, args: argparse.Namespace) -> dict:
    get_graph = COMPONENTS.get("get_graph")
    if get_graph is None:
        return {
            "available": False,
            "error": IMPORT_ERRORS.get("get_graph", "get_graph unavailable"),
            "stats": {},
            "seed_entities": [],
            "related_entities": [],
            "related_memories": [],
            "entity_probes": [],
        }

    graph = _safe_call(get_graph, default=None)
    if graph is None:
        return {
            "available": False,
            "error": "graph init failed",
            "stats": {},
            "seed_entities": [],
            "related_entities": [],
            "related_memories": [],
            "entity_probes": [],
        }

    stats = _safe_call(graph.get_stats, default={}) or {}
    mem_ids = [hit["id"] for hit in memory_hits if hit.get("id")][: args.graph_seed_limit]
    entity_map = _safe_call(graph.get_entities_for_memories, mem_ids, default={}) if mem_ids else {}
    seed_entities: list[str] = []
    for hit in memory_hits:
        for entity in hit.get("entities") or []:
            if entity and entity not in seed_entities:
                seed_entities.append(entity)
    for entity_list in (entity_map or {}).values():
        for entity in entity_list or []:
            if entity and entity not in seed_entities:
                seed_entities.append(entity)
    if not seed_entities:
        seed_entities = _fallback_entities(run, primary_query)

    related_entities = []
    if seed_entities:
        related_entities = _safe_call(
            graph.get_related_entities,
            seed_entities[: args.graph_seed_limit],
            default=[],
            top_k=args.graph_top_k,
        ) or []

    related_memories = []
    if mem_ids and seed_entities:
        related_memories = _safe_call(
            graph.search_related_new,
            mem_ids[: args.graph_seed_limit],
            seed_entities[: args.graph_seed_limit],
            default=[],
            max_candidates=args.graph_top_k * 2,
        ) or []

    entity_probes = []
    for entity in seed_entities[: min(3, args.graph_seed_limit)]:
        probe = _safe_call(graph.search_entity, entity, default=None)
        if isinstance(probe, dict) and probe.get("exists"):
            entity_probes.append(
                {
                    "name": probe.get("name", entity),
                    "type": probe.get("type", ""),
                    "memory_count": len(probe.get("memories", [])),
                    "related_entities": probe.get("related_entities", [])[: args.graph_top_k],
                    "memories": probe.get("memories", [])[: args.graph_top_k],
                }
            )

    return {
        "available": True,
        "stats": stats,
        "seed_entities": seed_entities[: args.graph_seed_limit],
        "entity_map": entity_map,
        "related_entities": related_entities[: args.graph_top_k],
        "related_memories": related_memories[: args.graph_top_k],
        "entity_probes": entity_probes,
    }


def _collect_scene_signals(primary_query: str, memory_hits: list[dict], run: dict, graph_signals: dict, args: argparse.Namespace) -> dict:
    get_scene_graph = COMPONENTS.get("get_scene_graph")
    get_scene_diffusion = COMPONENTS.get("get_scene_diffusion")
    if get_scene_graph is None:
        return {
            "available": False,
            "error": IMPORT_ERRORS.get("get_scene_graph", "get_scene_graph unavailable"),
            "stats": {},
            "anchor_neighbors": [],
            "scene_neighbors": [],
            "diffusion_hits": [],
        }

    scene_graph = _safe_call(get_scene_graph, default=None)
    if scene_graph is None:
        return {
            "available": False,
            "error": "scene_graph init failed",
            "stats": {},
            "anchor_neighbors": [],
            "scene_neighbors": [],
            "diffusion_hits": [],
        }

    stats = _safe_call(scene_graph.get_stats, default={}) or {}
    seed_entities = graph_signals.get("seed_entities") or _fallback_entities(run, primary_query)
    anchor_neighbors = []
    if seed_entities:
        anchor_neighbors = _safe_call(
            scene_graph.get_anchor_neighbors,
            seed_entities[: args.scene_anchor_limit],
            default=[],
            limit=args.scene_top_k * 3,
        ) or []

    scene_neighbors = []
    for scene_id, _weight in anchor_neighbors[: args.scene_top_k]:
        neighbors = _safe_call(scene_graph.get_scene_neighbors, scene_id, default=[], limit=args.scene_top_k)
        if neighbors:
            scene_neighbors.append({"scene_id": scene_id, "neighbors": neighbors})

    diffusion_hits = []
    if get_scene_diffusion is not None:
        scene_diffusion = _safe_call(get_scene_diffusion, default=None)
        if scene_diffusion is not None and memory_hits:
            diffusion_hits = _safe_call(
                scene_diffusion.search,
                primary_query,
                memory_hits[: args.scene_seed_limit],
                default=[],
                top_k=args.scene_top_k,
                with_trace=True,
            ) or []

    return {
        "available": True,
        "stats": stats,
        "anchor_neighbors": [
            {"scene_id": scene_id, "weight": weight}
            for scene_id, weight in anchor_neighbors[: args.scene_top_k]
        ],
        "scene_neighbors": scene_neighbors[: args.scene_top_k],
        "diffusion_hits": diffusion_hits[: args.scene_top_k],
    }


def _collect_causal_signals(
    recent_runs: list[dict],
    latest_run: dict,
    primary_query: str,
    run_query: str,
    args: argparse.Namespace,
) -> dict:
    get_causal_store = COMPONENTS.get("get_causal_store")
    sync_recent_runs = COMPONENTS.get("sync_recent_runs")
    if get_causal_store is None or sync_recent_runs is None:
        return {
            "available": False,
            "error": "causal store unavailable",
            "stats": {},
            "sync": {},
            "recent_events": [],
            "recent_relations": [],
            "matched_relations": [],
        }

    store = _safe_call(get_causal_store, default=None)
    if store is None:
        return {
            "available": False,
            "error": "causal store init failed",
            "stats": {},
            "sync": {},
            "recent_events": [],
            "recent_relations": [],
            "matched_relations": [],
        }

    sync_result = {
        "ok": False,
        "ingested": 0,
        "new_relations": 0,
        "writer": "",
        "disabled": not args.sync_causal,
    }
    if args.sync_causal:
        sync_result = _safe_call(
            sync_recent_runs,
            recent_runs,
            default=sync_result,
            max_new_runs=args.causal_max_new_runs,
            history_window=args.causal_history_window,
            force=args.causal_force,
            llm_timeout=args.causal_timeout,
        ) or sync_result
        sync_result["disabled"] = False

    stats = _safe_call(store.get_stats, default={}) or {}
    recent_events = _safe_call(store.get_recent_events, default=[], limit=args.causal_preview_limit) or []
    recent_relations = _safe_call(store.get_recent_relations, default=[], limit=args.causal_preview_limit) or []

    terms: list[str] = []
    for value in [
        latest_run.get("selected_activity", ""),
        latest_run.get("stop_reason", ""),
        latest_run.get("tick_type", ""),
        primary_query,
        run_query,
    ]:
        text = str(value).strip()
        if text and text not in terms:
            terms.append(text)
    for action in latest_run.get("actions", [])[:4]:
        text = str(action).strip()
        if text and text not in terms:
            terms.append(text)

    matched_relations = _safe_call(
        store.search_relations,
        terms,
        default=[],
        limit=args.causal_preview_limit,
    ) or []

    return {
        "available": True,
        "stats": stats,
        "sync": sync_result,
        "recent_events": recent_events[: args.causal_preview_limit],
        "recent_relations": recent_relations[: args.causal_preview_limit],
        "matched_relations": matched_relations[: args.causal_preview_limit],
    }


def _top_item(items: list[dict], score_keys: tuple[str, ...] = ("score", "spread_score", "activation")) -> dict | None:
    if not items:
        return None
    best = None
    best_score = -1.0
    for item in items:
        score = 0.0
        for key in score_keys:
            score = max(score, _to_score(item.get(key), 0.0))
        if score > best_score:
            best = item
            best_score = score
    return best


def _score_graph_related_memories(items: list[dict]) -> float:
    if not items:
        return 0.0
    scores = [min(1.0, _to_score(item.get("spread_score"), 0.0)) for item in items]
    return max(scores) if scores else 0.0


def _compose_prediction(
    run: dict,
    primary_query: str,
    run_query: str,
    causal: dict,
    procedural: dict,
    memory: dict,
    graph: dict,
    scene: dict,
) -> dict:
    causal_matches = causal.get("matched_relations", [])
    top_causal = _top_item(causal_matches, score_keys=("score", "confidence"))
    procedure_matches = procedural.get("procedure_matches", [])
    top_procedure = _top_item(procedure_matches, score_keys=("score",))
    top_memory = _top_item(memory.get("hits", []), score_keys=("score", "spread_score"))
    top_graph = _top_item(graph.get("related_memories", []), score_keys=("spread_score", "score"))
    top_scene = _top_item(scene.get("diffusion_hits", []), score_keys=("score",))

    selected_activity = run.get("selected_activity") or run.get("stop_reason") or run.get("mode") or "reflect"
    stop_reason = run.get("stop_reason", "")
    run_summary = _summarize_run(run)
    run_state = "stable" if stop_reason in {"ready", "completed"} else "uncertain"
    primary_action = selected_activity
    rationale: list[str] = []
    evidence: list[dict] = []

    if top_procedure:
        action_hint = top_procedure.get("action_hint") or (top_procedure.get("step_preview") or [""])[0] or selected_activity
        primary_action = action_hint or primary_action
        rationale.append(
            f"procedure match {top_procedure.get('template_id', '')} score={top_procedure.get('score', 0):.3f}"
        )
        evidence.append(
            {
                "source": "procedure",
                "score": top_procedure.get("score", 0.0),
                "text": f"{top_procedure.get('reason', '')} | {' -> '.join(top_procedure.get('step_preview', []) or [])}",
            }
        )

    if top_memory:
        memory_text = str(top_memory.get("text", ""))[:240]
        rationale.append(f"memory hit {top_memory.get('id', '')}")
        evidence.append(
            {
                "source": "memory",
                "score": top_memory.get("score", 0.0),
                "text": memory_text,
            }
        )

    if top_graph:
        rationale.append(f"graph spread score={top_graph.get('spread_score', 0.0):.3f}")
        evidence.append(
            {
                "source": "graph",
                "score": top_graph.get("spread_score", 0.0),
                "text": str(top_graph.get("text", ""))[:240],
            }
        )

    if top_scene:
        rationale.append(f"scene diffusion score={top_scene.get('score', 0.0):.3f}")
        evidence.append(
            {
                "source": "scene",
                "score": top_scene.get("score", 0.0),
                "text": f"{top_scene.get('id', '')} | {top_scene.get('trace', {}).get('relation_type', '')}",
            }
        )

    if top_causal:
        causal_score = _clamp01(top_causal.get("score", top_causal.get("confidence", 0.0)), 0.0)
        rationale.append(
            f"causal match {top_causal.get('relation_id', '')} score={causal_score:.3f}"
        )
        evidence.append(
            {
                "source": "causal",
                "score": causal_score,
                "text": f"{top_causal.get('cause', '')} -> {top_causal.get('effect', '')} ({top_causal.get('relation_type', '')})",
            }
        )

    if not rationale:
        rationale.append("sparse evidence -> conservative fallback")

    procedure_score = _clamp01(top_procedure.get("score", 0.0) if top_procedure else 0.0, 0.0)
    memory_score = _clamp01(top_memory.get("score", 0.0) if top_memory else 0.0, 0.0)
    graph_score = _score_graph_related_memories(graph.get("related_memories", []))
    scene_score = _clamp01(top_scene.get("score", 0.0) if top_scene else 0.0, 0.0)
    causal_score = _clamp01(top_causal.get("score", top_causal.get("confidence", 0.0)) if top_causal else 0.0, 0.0)
    run_score = _clamp01(
        0.7 if stop_reason in {"ready", "completed"} else 0.5 if stop_reason in {"sleep", "abort"} else 0.55,
        0.55,
    )

    weights = []
    if top_procedure:
        weights.append((procedure_score, 0.35))
    if top_memory:
        weights.append((memory_score, 0.25))
    if graph.get("related_memories"):
        weights.append((graph_score, 0.2))
    if top_scene:
        weights.append((scene_score, 0.15))
    if top_causal:
        weights.append((causal_score, 0.18))
    weights.append((run_score, 0.1))

    total_weight = sum(weight for _score, weight in weights) or 1.0
    confidence = sum(score * weight for score, weight in weights) / total_weight
    confidence = max(0.0, min(1.0, confidence))

    top_proc_risk = str((top_procedure or {}).get("risk_level", "low"))
    if confidence >= 0.7 and top_proc_risk != "high":
        risk_level = "low"
    elif confidence >= 0.45 and top_proc_risk != "high":
        risk_level = "medium"
    else:
        risk_level = "high"
    if top_proc_risk == "high":
        risk_level = "high"

    if top_causal and causal_score >= 0.6:
        summary = (
            f"Causal evidence suggests `{top_causal.get('cause', '')}` tends to lead to "
            f"`{top_causal.get('effect', '')}`. The next step is probably a nearby state transition."
        )
    elif top_procedure and procedure_score >= 0.55:
        summary = (
            f"Existing procedure memory points toward `{primary_action}`. "
            f"Near-term behavior looks like a short, repeatable pattern rather than a novel branch."
        )
    elif top_scene and scene_score >= 0.35:
        summary = (
            "Scene diffusion found a similar contextual cluster, so the next state likely follows "
            "a familiar path with moderate uncertainty."
        )
    elif top_memory:
        summary = (
            "Semantic recall is the strongest signal. The system probably needs one more retrieval "
            "step before it can make a stable decision."
        )
    else:
        summary = (
            "Evidence is sparse. The safest prediction is to hold position, gather more context, "
            "and avoid high-risk actions."
        )

    alternatives: list[dict] = []
    for match in procedure_matches[:3]:
        if not isinstance(match, dict):
            continue
        action = match.get("action_hint") or (match.get("step_preview") or [""])[0] or "reflect"
        alternatives.append(
            {
                "action": action,
                "score": round(_clamp01(match.get("score", 0.0), 0.0), 3),
                "reason": str(match.get("reason", ""))[:120],
            }
        )
    if not alternatives:
        alternatives = [
            {"action": "wait", "score": 0.5, "reason": "fallback"},
            {"action": "reflect", "score": 0.45, "reason": "fallback"},
            {"action": "recall_memory", "score": 0.4, "reason": "fallback"},
        ]

    verdict = "lightweight_world_model_feasible" if confidence >= 0.4 and len(evidence) >= 2 else "needs_more_structure"

    return {
        "summary": summary,
        "confidence": round(confidence, 3),
        "risk_level": risk_level,
        "selected_action": primary_action,
        "run_state": run_state,
        "verdict": verdict,
        "rationale": rationale,
        "evidence": evidence,
        "alternatives": alternatives,
        "run_summary": run_summary,
        "queries": {
            "primary_query": primary_query,
            "run_query": run_query,
        },
    }


def _build_capability_report(report: dict) -> dict:
    proc = report.get("procedural", {})
    mem = report.get("memory", {})
    graph = report.get("graph", {})
    scene = report.get("scene", {})
    causal = report.get("causal", {})
    prediction = report.get("prediction", {})

    available_sources = {
        "event_log": bool(report.get("latest_run")),
        "procedural_memory": bool(proc.get("counts")),
        "memory_search": bool(mem.get("hits")),
        "graph": bool(graph.get("available")),
        "scene_graph": bool(scene.get("available")),
        "causal_store": bool(causal.get("available")),
    }
    score = sum(1 for ok in available_sources.values() if ok) / max(len(available_sources), 1)
    if prediction.get("verdict") == "lightweight_world_model_feasible":
        score = min(1.0, score + 0.1)

    return {
        "can_build_lightweight_world_model": score >= 0.6,
        "coverage_score": round(score, 3),
        "available_sources": available_sources,
        "missing_components": [name for name, ok in available_sources.items() if not ok],
    }


def build_report(args: argparse.Namespace) -> dict:
    event_log = COMPONENTS.get("get_event_log")
    event_log = _safe_call(event_log, default=None) if event_log is not None else None
    latest_run, recent_runs, run_source = _latest_run(event_log, args.recent_runs, args.run_id)
    primary_query = _build_primary_query(args, latest_run)
    run_query = _build_run_query(latest_run)

    causal = _collect_causal_signals(recent_runs, latest_run, primary_query, run_query, args)
    procedural = _collect_procedural_signals(latest_run, args)
    memory = _collect_memory_signals(primary_query, run_query, args)
    graph = _collect_graph_signals(latest_run, memory["hits"], primary_query, args)
    scene = _collect_scene_signals(primary_query, memory["hits"], latest_run, graph, args)
    prediction = _compose_prediction(latest_run, primary_query, run_query, causal, procedural, memory, graph, scene)

    report = {
        "meta": {
            "repo_root": str(ROOT),
            "backend_path": str(BACKEND),
            "run_source": run_source,
            "import_errors": IMPORT_ERRORS,
        },
        "latest_run": _summarize_run(latest_run),
        "recent_runs": [_summarize_run(run) for run in recent_runs[- args.recent_runs :]],
        "causal": causal,
        "procedural": procedural,
        "memory": memory,
        "graph": graph,
        "scene": scene,
        "prediction": prediction,
    }
    report["capability"] = _build_capability_report(report)
    return report


def _print_summary(report: dict) -> None:
    latest = report.get("latest_run", {})
    prediction = report.get("prediction", {})
    causal = report.get("causal", {})
    proc = report.get("procedural", {})
    mem = report.get("memory", {})
    graph = report.get("graph", {})
    scene = report.get("scene", {})
    capability = report.get("capability", {})

    print("World Model Demo")
    print(f"  run: {latest.get('run_id', '-')}")
    print(
        f"  context: mode={latest.get('mode', '-')}, activity={latest.get('selected_activity', '-')}, "
        f"stop_reason={latest.get('stop_reason', '-')}, tick={latest.get('tick_type', '-')}"
    )
    print(f"  query: {prediction.get('queries', {}).get('primary_query', '-')}")
    print(
        "  signals: "
        f"causal={len(causal.get('matched_relations', []))}, "
        f"seed_relations={causal.get('stats', {}).get('seed_relation_count', 0)}, "
        f"procedures={len(proc.get('procedure_matches', []))}, "
        f"examples={len(proc.get('examples', []))}, "
        f"memory={len(mem.get('hits', []))}, "
        f"graph={len(graph.get('related_memories', []))}, "
        f"scene={len(scene.get('diffusion_hits', []))}"
    )
    print(
        f"  prediction: {prediction.get('summary', '-')}\n"
        f"  selected_action: {prediction.get('selected_action', '-')}\n"
        f"  confidence: {prediction.get('confidence', 0.0):.3f} | risk={prediction.get('risk_level', '-')}\n"
        f"  verdict: {prediction.get('verdict', '-')}\n"
        f"  capability: {capability.get('coverage_score', 0.0):.3f} | "
        f"feasible={capability.get('can_build_lightweight_world_model', False)}"
    )

    if prediction.get("rationale"):
        print("  rationale:")
        for item in prediction["rationale"][:5]:
            print(f"    - {item}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AiBrain world model demo")
    parser.add_argument("--query", default="", help="Override the primary semantic query")
    parser.add_argument("--run-id", default="", help="Inspect a specific run id")
    parser.add_argument("--recent-runs", type=int, default=8, help="How many recent runs to load")
    parser.add_argument("--example-window", type=int, default=24, help="How many runs to collect for procedural preview")
    parser.add_argument("--procedure-top-k", type=int, default=3, help="Top procedural matches to keep")
    parser.add_argument("--memory-top-k", type=int, default=6, help="Top memory hits to keep")
    parser.add_argument("--graph-top-k", type=int, default=6, help="Top graph candidates to keep")
    parser.add_argument("--graph-seed-limit", type=int, default=5, help="Limit graph seed entities and memory ids")
    parser.add_argument("--scene-top-k", type=int, default=5, help="Top scene candidates to keep")
    parser.add_argument("--scene-seed-limit", type=int, default=8, help="How many semantic hits feed scene diffusion")
    parser.add_argument("--scene-anchor-limit", type=int, default=5, help="How many anchor seeds to use for scene graph lookup")
    parser.add_argument("--sync-causal", action=argparse.BooleanOptionalAction, default=True, help="Sync recent runs into the causal store")
    parser.add_argument("--causal-max-new-runs", type=int, default=1, help="Max new runs to write into causal store per execution")
    parser.add_argument("--causal-history-window", type=int, default=2, help="How many previous runs to include as LLM context")
    parser.add_argument("--causal-preview-limit", type=int, default=5, help="How many causal items to keep in the report")
    parser.add_argument("--causal-timeout", type=int, default=15, help="LLM timeout seconds for causal writing")
    parser.add_argument("--causal-force", action="store_true", help="Re-write causal data even if the run was already ingested")
    parser.add_argument("--mine-support", type=int, default=2, help="Minimum support for procedural mining preview")
    parser.add_argument("--mine-success-rate", type=float, default=0.5, help="Minimum success rate for procedural mining preview")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON after the summary")
    parser.add_argument("--output", default="", help="Optional path to save the full JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    _print_summary(report)

    if args.json:
        print()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
