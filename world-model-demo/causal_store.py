#!/usr/bin/env python3
"""Persistent local causal store for the world-model demo.

The store keeps two append-only JSONL files:
  - causal_events.jsonl
  - causal_relations.jsonl

It also loads an optional seed overlay from:
  - causal_seed_relations.jsonl

It also maintains a small state JSON checkpoint so the demo can ingest only
new runs on subsequent executions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from causal_writer import build_causal_packet


logger = logging.getLogger("world_model_demo.causal_store")

DATA_DIR = Path(__file__).resolve().parent / "data"
EVENTS_FILE = DATA_DIR / "causal_events.jsonl"
RELATIONS_FILE = DATA_DIR / "causal_relations.jsonl"
SEED_RELATIONS_FILE = DATA_DIR / "causal_seed_relations.jsonl"
STATE_FILE = DATA_DIR / "causal_state.json"

_INSTANCE: "CausalStore | None" = None
_INSTANCE_LOCK = threading.Lock()


class CausalStore:
    """Append-only causal memory for run-level event and relation writes."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self._data_dir = data_dir
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._relations: list[dict] = []
        self._seed_relations: list[dict] = []
        self._seen_run_ids: set[str] = set()
        self._seen_relation_ids: set[str] = set()
        self._state = {
            "last_processed_run_id": "",
            "last_ingested_at": "",
            "event_count": 0,
            "relation_count": 0,
            "llm_writes": 0,
            "fallback_writes": 0,
        }
        self._load()

    # ── load / persist ──────────────────────────────────────

    def _ensure_dir(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        self._ensure_dir()
        self._load_state()
        self._load_events()
        self._load_relations()
        self._load_seed_relations()

    def _load_state(self) -> None:
        if not STATE_FILE.is_file():
            return
        try:
            self._state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            logger.warning("[causal_store] failed to load state")

    def _load_events(self) -> None:
        if not EVENTS_FILE.is_file():
            return
        try:
            with EVENTS_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        continue
                    self._events.append(item)
                    run_id = str(item.get("run_id", "")).strip()
                    if run_id:
                        self._seen_run_ids.add(run_id)
        except (OSError, json.JSONDecodeError):
            logger.warning("[causal_store] failed to load events")

    def _load_relations(self) -> None:
        if not RELATIONS_FILE.is_file():
            return
        try:
            with RELATIONS_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        continue
                    self._relations.append(item)
                    relation_id = str(item.get("relation_id", "")).strip()
                    if relation_id:
                        self._seen_relation_ids.add(relation_id)
        except (OSError, json.JSONDecodeError):
            logger.warning("[causal_store] failed to load relations")

    def _load_seed_relations(self) -> None:
        if not SEED_RELATIONS_FILE.is_file():
            return
        try:
            with SEED_RELATIONS_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        continue
                    self._relations.append(item)
                    self._seed_relations.append(item)
                    relation_id = str(item.get("relation_id", "")).strip()
                    if relation_id:
                        self._seen_relation_ids.add(relation_id)
        except (OSError, json.JSONDecodeError):
            logger.warning("[causal_store] failed to load seed relations")

    def _persist_state(self) -> None:
        self._ensure_dir()
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)

    def _append_jsonl(self, path: Path, record: dict) -> None:
        self._ensure_dir()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── public api ─────────────────────────────────────────

    def has_run(self, run_id: str) -> bool:
        return str(run_id).strip() in self._seen_run_ids

    def ingest_runs(
        self,
        runs: list[dict],
        *,
        max_new_runs: int = 1,
        history_window: int = 2,
        force: bool = False,
        llm_timeout: int = 15,
    ) -> dict:
        """Ingest unseen runs from a recent window.

        The newest unseen runs are processed first so the store behaves like an
        incremental writer rather than a full backfiller.
        """
        if not runs:
            return {
                "ok": True,
                "ingested": 0,
                "skipped": 0,
                "new_events": 0,
                "new_relations": 0,
                "writer": "",
            }

        candidates = []
        for idx, run in enumerate(runs):
            run_id = str(run.get("run_id", "")).strip()
            if not run_id:
                continue
            if force or run_id not in self._seen_run_ids:
                candidates.append((idx, run))

        if max_new_runs > 0:
            candidates = candidates[-max_new_runs:]

        if not candidates:
            return {
                "ok": True,
                "ingested": 0,
                "skipped": len(runs),
                "new_events": 0,
                "new_relations": 0,
                "writer": "",
            }

        ingested = 0
        new_relations = 0
        writers: list[str] = []
        last_run_id = ""

        with self._lock:
            for idx, run in candidates:
                run_id = str(run.get("run_id", "")).strip()
                history = list(runs[max(0, idx - history_window):idx])
                packet = build_causal_packet(run, history=history, timeout=llm_timeout)
                event_record = self._build_event_record(run, packet)
                relation_records = self._build_relation_records(run, packet)

                if run_id in self._seen_run_ids and not force:
                    continue

                self._events.append(event_record)
                self._append_jsonl(EVENTS_FILE, event_record)
                self._seen_run_ids.add(run_id)
                ingested += 1
                last_run_id = run_id
                writers.append(str(packet.get("writer", "")))

                for relation_record in relation_records:
                    relation_id = relation_record["relation_id"]
                    if relation_id in self._seen_relation_ids:
                        continue
                    self._relations.append(relation_record)
                    self._append_jsonl(RELATIONS_FILE, relation_record)
                    self._seen_relation_ids.add(relation_id)
                    new_relations += 1

                if packet.get("writer") == "llm":
                    self._state["llm_writes"] = int(self._state.get("llm_writes", 0)) + 1
                else:
                    self._state["fallback_writes"] = int(self._state.get("fallback_writes", 0)) + 1

            if last_run_id:
                self._state["last_processed_run_id"] = last_run_id
                self._state["last_ingested_at"] = _now_iso()
            self._state["event_count"] = len(self._events)
            self._state["relation_count"] = len(self._relations)
            self._persist_state()

        return {
            "ok": True,
            "ingested": ingested,
            "skipped": max(0, len(runs) - ingested),
            "new_events": ingested,
            "new_relations": new_relations,
            "writer": _majority_writer(writers),
            "last_processed_run_id": last_run_id,
        }

    def search_relations(self, terms: list[str], limit: int = 5) -> list[dict]:
        """Return causal relations that match any query term."""
        if not terms:
            return self.get_recent_relations(limit)

        normalized_terms = [str(term).strip().lower() for term in terms if str(term).strip()]
        if not normalized_terms:
            return self.get_recent_relations(limit)

        scored: list[tuple[float, dict]] = []
        for index, relation in enumerate(reversed(self._relations)):
            haystack = " ".join(
                [
                    str(relation.get("cause", "")),
                    str(relation.get("effect", "")),
                    str(relation.get("relation_type", "")),
                    str(relation.get("evidence", "")),
                    str(relation.get("summary", "")),
                ]
            ).lower()
            hit_count = sum(1 for term in normalized_terms if term in haystack)
            if hit_count == 0:
                continue
            score = _clamp01(relation.get("confidence", 0.5))
            score += hit_count * 0.12
            score += min(0.12, 0.04 / max(index + 1, 1))
            scored.append((score, dict(relation, score=round(min(1.0, score), 3))))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def get_recent_relations(self, limit: int = 5) -> list[dict]:
        return list(reversed(self._relations[-limit:]))

    def get_recent_events(self, limit: int = 5) -> list[dict]:
        return list(reversed(self._events[-limit:]))

    def get_stats(self) -> dict:
        return {
            "event_count": len(self._events),
            "relation_count": len(self._relations),
            "seed_relation_count": len(self._seed_relations),
            "last_processed_run_id": self._state.get("last_processed_run_id", ""),
            "last_ingested_at": self._state.get("last_ingested_at", ""),
            "llm_writes": self._state.get("llm_writes", 0),
            "fallback_writes": self._state.get("fallback_writes", 0),
        }

    def sync_recent_runs(
        self,
        runs: list[dict],
        *,
        max_new_runs: int = 1,
        history_window: int = 2,
        force: bool = False,
        llm_timeout: int = 15,
    ) -> dict:
        return self.ingest_runs(
            runs,
            max_new_runs=max_new_runs,
            history_window=history_window,
            force=force,
            llm_timeout=llm_timeout,
        )

    # ── internal builders ───────────────────────────────────

    def _build_event_record(self, run: dict, packet: dict) -> dict:
        run_id = str(run.get("run_id", "")).strip()
        event = packet.get("event") if isinstance(packet, dict) else {}
        if not isinstance(event, dict):
            event = {}
        return {
            "event_id": f"cev_{run_id}",
            "run_id": run_id,
            "mode": run.get("mode", ""),
            "tick_type": (run.get("trigger") or {}).get("tick_type", ""),
            "selected_activity": run.get("selected_activity", ""),
            "stop_reason": run.get("stop_reason", ""),
            "summary": event.get("summary", ""),
            "state": event.get("state", {}),
            "writer": packet.get("writer", "fallback"),
            "llm_used": bool(packet.get("llm_used", False)),
            "created_at": _now_iso(),
        }

    def _build_relation_records(self, run: dict, packet: dict) -> list[dict]:
        run_id = str(run.get("run_id", "")).strip()
        relations = packet.get("relations") if isinstance(packet, dict) else []
        if not isinstance(relations, list):
            relations = []
        records = []
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                continue
            cause = str(relation.get("cause", "")).strip()
            effect = str(relation.get("effect", "")).strip()
            relation_type = str(relation.get("relation_type", "associated")).strip().lower()
            confidence = _clamp01(relation.get("confidence", 0.5))
            if not cause or not effect or cause == effect:
                continue
            if relation_type not in {
                "causal",
                "temporal",
                "conditional",
                "enables",
                "blocks",
                "associated",
            }:
                relation_type = "associated"
            relation_id = _relation_id(run_id, cause, effect, relation_type, index)
            records.append(
                {
                    "relation_id": relation_id,
                    "event_id": f"cev_{run_id}",
                    "run_id": run_id,
                    "cause": cause,
                    "effect": effect,
                    "relation_type": relation_type,
                    "confidence": round(confidence, 3),
                    "evidence": str(relation.get("evidence", ""))[:240],
                    "writer": packet.get("writer", "fallback"),
                    "llm_used": bool(packet.get("llm_used", False)),
                    "created_at": _now_iso(),
                }
            )
        return records


def get_causal_store() -> CausalStore:
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = CausalStore()
    return _INSTANCE


def sync_recent_runs(
    runs: list[dict],
    *,
    max_new_runs: int = 1,
    history_window: int = 2,
    force: bool = False,
    llm_timeout: int = 15,
) -> dict:
    store = get_causal_store()
    return store.sync_recent_runs(
        runs,
        max_new_runs=max_new_runs,
        history_window=history_window,
        force=force,
        llm_timeout=llm_timeout,
    )


def _relation_id(run_id: str, cause: str, effect: str, relation_type: str, index: int) -> str:
    raw = f"{run_id}|{cause}|{effect}|{relation_type}|{index}"
    return "cr_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _majority_writer(writers: list[str]) -> str:
    if not writers:
        return ""
    counts: dict[str, int] = {}
    for writer in writers:
        counts[writer] = counts.get(writer, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))
