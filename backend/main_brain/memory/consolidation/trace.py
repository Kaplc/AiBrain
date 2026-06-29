"""运行轨迹与检查点持久化（T010 / FR-006 / FR-011）

两层持久化：
  1. ConsolidationState（检查点）→ internal_state.json['memory_consolidation']，
     经 get_state().transaction() 原子落盘。含 last_processed_seq / seen_hashes /
     last_run_id 等，保证重启后增量不重复沉淀。
  2. ConsolidationRun + 每条候选决策 → logs/main_brain/consolidation_runs.jsonl
     （可回放）+ 内存 ring buffer（供 /recent 快速取）。

全程 best-effort：trace 落盘失败绝不阻断沉淀主流程。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque

from .contracts import ConsolidationState, ConsolidationRun, POLICY_VERSION

logger = logging.getLogger("memory.consolidation.trace")

_STATE_NODE = "memory_consolidation"
_SEEN_HASH_CAP = 500          # seen_hashes 上限（FIFO 淘汰）
_RECENT_RUN_CAP = 100         # 内存 ring buffer 上限

# 日志根目录：backend/logs/main_brain/（与 brain_runs.jsonl 同目录）
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "logs", "main_brain",
)
_LOG_PATH = os.path.join(_LOG_DIR, "consolidation_runs.jsonl")


class TraceStore:
    """检查点 + 运行轨迹单例。"""

    _instance = None
    _cls_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.RLock()
        self._recent: deque[dict] = deque(maxlen=_RECENT_RUN_CAP)

    @classmethod
    def get_instance(cls) -> "TraceStore":
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 检查点（ConsolidationState）──────────────────────────
    def get_state(self) -> ConsolidationState:
        try:
            from main_brain.state import get_state
            data = get_state().snapshot()
            node = data.get(_STATE_NODE)
            if isinstance(node, dict):
                return ConsolidationState.from_dict(node)
        except Exception as e:
            logger.warning(f"[trace] read state failed: {e}")
        return ConsolidationState()

    def update_state(self, fn) -> ConsolidationState:
        """在事务内读改写 memory_consolidation 节点。fn(state) -> None（原地改）。"""
        try:
            from main_brain.state import get_state
            with get_state().transaction() as data:
                node = data.setdefault(_STATE_NODE, {})
                state = ConsolidationState.from_dict(node)
                fn(state)
                # seen_hashes 截断
                if len(state.seen_hashes) > _SEEN_HASH_CAP:
                    state.seen_hashes = state.seen_hashes[-_SEEN_HASH_CAP:]
                data[_STATE_NODE] = state.to_dict()
                return state
        except Exception as e:
            logger.warning(f"[trace] update state failed: {e}")
            return self.get_state()

    def add_seen_hashes(self, hashes: list[str]) -> None:
        """批量记录已沉淀的 source_hash。"""
        if not hashes:
            return
        def _fn(state: ConsolidationState) -> None:
            existing = set(state.seen_hashes)
            for h in hashes:
                if h and h not in existing:
                    state.seen_hashes.append(h)
                    existing.add(h)
        self.update_state(_fn)

    def seen_hash_set(self) -> set[str]:
        return set(self.get_state().seen_hashes)

    def next_run_id(self) -> str:
        """生成递增 run_id：mc_<stamp>_<seq>。"""
        from main_brain import clock as times
        stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")[:15]
        seq_box = [0]

        def _fn(state: ConsolidationState) -> None:
            state.run_seq = int(state.run_seq or 0) + 1
            state.policy_version = POLICY_VERSION
            seq_box[0] = state.run_seq

        self.update_state(_fn)
        return f"mc_{stamp}_{seq_box[0]:04d}"

    # ── 运行轨迹（JSONL + ring buffer）───────────────────────
    def append_run(self, run: ConsolidationRun, candidates: list[dict] | None = None) -> None:
        """记录一次运行。摘要进 ring buffer，完整（含候选 trace）写 JSONL。"""
        summary = run.to_dict()
        summary["candidate_count"] = run.candidate_count
        with self._lock:
            self._recent.append(summary)
        record = dict(summary)
        # 候选 trace 只写前若干条（可观测，避免巨型 JSONL）
        if candidates:
            record["candidates"] = candidates[:30]
        record.setdefault("logged_at", _now_iso())
        try:
            self._write_jsonl(record)
        except Exception as e:
            logger.warning(f"[trace] append_run jsonl failed: {e}")

    def _write_jsonl(self, record: dict) -> None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def recent_runs(self, limit: int = 20) -> list[dict]:
        """最近运行摘要（内存，最新在前）。"""
        with self._lock:
            items = list(self._recent)
        items.reverse()
        return items[:limit]

    def log_path(self) -> str:
        return _LOG_PATH


def _now_iso() -> str:
    from main_brain import clock as times
    return times.now_iso()


def get_trace_store() -> TraceStore:
    return TraceStore.get_instance()
