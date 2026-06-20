"""brain_runs.jsonl 事件日志（T002）

每次 reactive/background run 结束后 append 一行 JSONL，支持回放和调试。
同时维护一个内存 ring buffer 供 /chat/state、runs/recent 快速取摘要。

写入约定（plan 第六节写入约束 #5）：所有写入都能从 brain_runs.jsonl 回溯到
对应 run 和 cycle。run 记录包含 run_id / mode / cycle 摘要 / stop_reason / error。

全程 try/except，日志失败绝不阻断循环。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger("main_brain.event_log")

# 日志根目录：与项目 1-logs 约定一致，放在 backend/logs/main_brain/
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "main_brain",
)
_LOG_PATH = os.path.join(_LOG_DIR, "brain_runs.jsonl")

# 内存 ring buffer 上限（够 /chat/state 与 runs/recent 用，不占太多内存）
_RECENT_CAP = 200


class BrainEventLog:
    """brain run 事件日志单例（JSONL 落盘 + 内存 ring buffer）。"""

    _instance = None
    _lock_cls = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._recent: deque[dict] = deque(maxlen=_RECENT_CAP)

    @classmethod
    def get_instance(cls) -> "BrainEventLog":
        if cls._instance is None:
            with cls._lock_cls:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 写入 ─────────────────────────────────────────────────
    def append_run(self, run_summary: dict, full: dict | None = None) -> None:
        """记录一次 run。summary 进 ring buffer，full 写 JSONL（可回放）。

        Args:
            run_summary: BrainRun.to_summary() 精简摘要。
            full: BrainRun.to_full() 完整轨迹（可选，None 时落 summary）。
        """
        record = full if full is not None else run_summary
        record = dict(record)  # 浅拷贝，避免外部改
        record.setdefault("logged_at", _now_iso())
        with self._lock:
            self._recent.append(run_summary)
        try:
            self._write_jsonl(record)
        except Exception as e:
            logger.warning(f"[event_log] append_run failed: {e}")

    def _write_jsonl(self, record: dict) -> None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ── 读取 ─────────────────────────────────────────────────
    def recent_runs(self, limit: int = 20, mode: str | None = None) -> list[dict]:
        """最近 run 摘要（内存，最新在前）。"""
        with self._lock:
            items = list(self._recent)
        items.reverse()
        if mode:
            items = [r for r in items if r.get("mode") == mode]
        return items[:limit]

    def get_run(self, run_id: str) -> dict | None:
        """从 JSONL 回读单个 run 的完整轨迹。不存在返回 None。"""
        if not run_id or not os.path.exists(_LOG_PATH):
            return None
        try:
            # 从文件尾部倒序找，命中即返（最新优先）
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("run_id") == run_id:
                    return rec
        except Exception as e:
            logger.warning(f"[event_log] get_run failed: {e}")
        return None

    def last_run_id(self, mode: str | None = None) -> str:
        """最近一次 run_id（供 /chat/state）。"""
        runs = self.recent_runs(limit=1, mode=mode)
        return runs[0].get("run_id", "") if runs else ""

    def log_path(self) -> str:
        return _LOG_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_event_log() -> BrainEventLog:
    return BrainEventLog.get_instance()
