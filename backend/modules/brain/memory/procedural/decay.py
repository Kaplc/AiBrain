"""程序记忆生命周期管理：衰减、冷却、退役、归档

核心策略：
  1. 衰减：长期不用的模板逐步降低 confidence
  2. 冷却：近期失败的模板短期降频（不参与匹配）
  3. 退役：连续低分或失败过多的模板标记为 deprecated
  4. 归档：退役后若再无使用记录，移入 archive

所有操作通过 ProcedureStore 完成，不直接操作文件。
"""

import datetime
import logging
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate, ProcedureState
from modules.brain.memory.procedural.store import ProcedureStore

logger = logging.getLogger("modules.brain.procedural.decay")

# ── 默认阈值 ────────────────────────────────────────────

DAYS_BEFORE_DECAY = 14          # 14 天未使用开始衰减
DECAY_FACTOR = 0.05             # 每次衰减 5%
MAX_FAILURE_RATE = 0.6          # 超过 60% 失败率退役
MIN_CONFIDENCE_ACTIVE = 0.3     # active 模板的最低置信度
COOLDOWN_TICKS = 5              # 冷却期后自动回 active 需要的连续成功次数
COOLDOWN_FAIL_LIMIT = 3         # 连续失败 N 次后冷却


def apply_decay(store: ProcedureStore, now: Optional[str] = None):
    """对所有 active/proposed/cooling 模板执行衰减检查

    对 last_used_at 超过 DAYS_BEFORE_DECAY 的模板降低 confidence。
    """
    if now is None:
        now = _now_iso()
    templates = store.get_all_templates()
    changed = []
    for t in templates:
        if t.status not in ("active", "proposed", "cooling"):
            continue
        if not t.last_used_at:
            continue
        days = _days_between(t.last_used_at, now)
        if days >= DAYS_BEFORE_DECAY:
            decay_count = int(days / DAYS_BEFORE_DECAY)
            factor = 1.0 - (DECAY_FACTOR * decay_count)
            t.confidence = max(0.0, t.confidence * factor)
            if t.confidence < MIN_CONFIDENCE_ACTIVE:
                t.status = "deprecated"
            changed.append(t)
    if changed:
        store.save_templates(changed)
        logger.info("[decay] aged %d templates (factor=%.2f)", len(changed), DECAY_FACTOR)


def check_feedback_decay(store: ProcedureStore, template_id: str):
    """反馈后检查模板是否需要冷却或退役"""
    t = store.get_template(template_id)
    if not t:
        return
    total = t.success_count + t.failure_count
    if total == 0:
        return
    failure_rate = t.failure_count / total

    changed = False
    if failure_rate >= MAX_FAILURE_RATE and t.status in ("active", "proposed", "cooling"):
        t.status = "deprecated"
        t.confidence = max(0.0, t.confidence * 0.5)
        changed = True
        logger.info("[decay] deprecated %s: fail_rate=%.2f >= %.2f", template_id, failure_rate, MAX_FAILURE_RATE)
    elif t.confidence < MIN_CONFIDENCE_ACTIVE and t.status == "active":
        t.status = "cooling"
        t.confidence = max(0.0, t.confidence * 0.8)
        changed = True
        logger.info("[decay] cooling %s: conf=%.2f < %.2f", template_id, t.confidence, MIN_CONFIDENCE_ACTIVE)
    elif t.confidence >= MIN_CONFIDENCE_ACTIVE and t.status == "cooling":
        t.status = "active"
        changed = True
        logger.info("[decay] restore %s: cooling -> active (conf=%.2f)", template_id, t.confidence)

    if changed:
        store.save_template(t)


def check_archive(store: ProcedureStore, max_inactive_days: int = 30):
    """将 deprecated 且长期不用的模板移入 archive"""
    now = _now_iso()
    archived = []
    for t in store.get_templates_by_status("deprecated"):
        if not t.last_used_at:
            continue
        days = _days_between(t.last_used_at, now)
        if days >= max_inactive_days:
            store.archive_template(t)
            archived.append(t.template_id)
    if archived:
        logger.info("[decay] archived %d deprecated templates (inactive > %d days)", len(archived), max_inactive_days)
    return archived


def refresh_state_counts(store: ProcedureStore):
    """刷新 count 字段到检查点"""
    counts = store.get_counts()
    store.update_state(
        active_count=counts["active"],
        draft_count=counts["draft"],
        archive_count=counts["archive"],
    )


# ── 辅助函数 ────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_between(iso_a: str, iso_b: str) -> float:
    try:
        a = datetime.datetime.fromisoformat(iso_a.replace("Z", "+00:00"))
        b = datetime.datetime.fromisoformat(iso_b.replace("Z", "+00:00"))
        return (b - a).days
    except (ValueError, TypeError):
        return 0.0
