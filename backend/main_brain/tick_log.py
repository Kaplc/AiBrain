"""Tick 日志 — 记录 Day Tick / Sleep Tick / Consciousness Tick 的持久化时间线

保存到 main_brain/data/tick_log.json，与 internal_state.json 同目录。
每种 tick 类型只保留**最新一次**记录，每次写入覆盖同类型的旧记录。

格式：
    {"consciousness": {"timestamp": "...", "details": {...}},
     "day_tick":      {"timestamp": "...", "details": {...}}}
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger("main_brain.tick_log")

_DATA_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data"
))
_TICK_LOG_PATH = os.path.join(_DATA_DIR, "tick_log.json")
_lock = threading.Lock()


def record_tick(tick_type: str, **details) -> None:
    """记录/覆盖一条 tick。线程安全。同类型只保留最新一条。"""
    from .clock import get_brain_clock
    entry = {
        "timestamp": get_brain_clock().now_iso_local(),
    }
    if details:
        entry["details"] = {k: v for k, v in details.items() if v is not None}

    with _lock:
        try:
            records = _load()
            records[tick_type] = entry
            _save(records)
        except Exception as e:
            logger.warning(f"[tick_log] record failed: {e}")


def last_tick_iso(tick_type: str) -> str:
    """返回指定 tick 类型的最新时间戳 ISO 字符串，无记录返回空串。"""
    with _lock:
        try:
            records = _load()
            entry = records.get(tick_type)
            if entry and isinstance(entry, dict):
                return entry.get("timestamp", "")
        except Exception:
            pass
    return ""


def all_ticks() -> dict:
    """返回全部最新 tick 记录（只读快照）。"""
    with _lock:
        return dict(_load())


def _load() -> dict:
    """从磁盘加载 tick_log.json，损坏/缺失返回空 dict。"""
    if not os.path.isfile(_TICK_LOG_PATH):
        return {}
    try:
        with open(_TICK_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"[tick_log] load failed, reset: {e}")
        return {}


def _save(records: dict) -> None:
    """原子写入 tick_log.json。"""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = _TICK_LOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _TICK_LOG_PATH)
    except OSError as e:
        logger.warning(f"[tick_log] save failed: {e}")
