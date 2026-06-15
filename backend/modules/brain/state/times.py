"""时间工具 — 状态层共用的时间计算（统一 UTC，避免各 Manager 各写一份）。"""
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def parse_iso(ts: str) -> datetime | None:
    """解析 ISO 时间字符串；无时区视作 UTC；失败返回 None。"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_since(ts: str) -> float:
    """距 ts 的天数（float）。无/坏时间戳返回大数（视为很久以前）。"""
    dt = parse_iso(ts)
    if dt is None:
        return 9999.0
    return max(0.0, (now() - dt).total_seconds() / 86400.0)


def hours_since(ts: str) -> float:
    dt = parse_iso(ts)
    if dt is None:
        return 9999.0
    return max(0.0, (now() - dt).total_seconds() / 3600.0)


def now_plus_hours_iso(hours: float) -> str:
    """now + hours 后的 ISO 字符串（用于 expire_at / refractory_until）。"""
    from datetime import timedelta
    return (now() + timedelta(hours=hours)).isoformat()
