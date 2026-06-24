"""反馈更新与奖励学习（T007）

根据执行结果更新模板的 success_count、failure_count、reward_ema、confidence，
并在指标恶化时自动触发冷却、降权或退役。
"""

import datetime
import logging
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureFeedback, TEMPLATE_STATUS
from modules.brain.memory.procedural.store import get_procedure_store
from modules.brain.memory.procedural.decay import check_feedback_decay

logger = logging.getLogger("main_brain.procedural.feedback")


def record_procedure_feedback(
    template_id: str,
    run_id: str,
    result: str,
    reward_delta: float,
    notes: str = "",
) -> dict:
    """记录一次模板反馈并更新统计。

    Args:
        template_id: 目标模板 ID。
        run_id: 来源 run_id。
        result: success / fail / partial / skip。
        reward_delta: -1.0 ~ 1.0 的奖励增量。
        notes: 可选说明。

    Returns:
        {"ok": bool, "template_id": str, "status": str, "changes": dict}
    """
    store = get_procedure_store()
    template = store.get_template(template_id)
    if not template:
        return {"ok": False, "reason": "template not found"}

    # 记录反馈
    feedback = ProcedureFeedback(
        template_id=template_id,
        run_id=run_id,
        result=result,
        reward_delta=reward_delta,
        notes=notes,
        recorded_at=_now_iso(),
    )

    # 更新统计
    changes = _apply_feedback(template, result, reward_delta)
    template.last_used_at = _now_iso()
    store.save_template(template)

    # 检查是否需要冷却或退役
    check_feedback_decay(store, template_id)

    # 重新读取最新状态
    updated = store.get_template(template_id)
    final_status = updated.status if updated else template.status

    logger.info(
        "[procedural.feedback] template=%s result=%s delta=%.2f status=%s",
        template_id, result, reward_delta, final_status,
    )

    return {
        "ok": True,
        "template_id": template_id,
        "status": final_status,
        "changes": changes,
    }


def _apply_feedback(template, result: str, reward_delta: float) -> dict:
    """将反馈应用到模板统计字段。"""
    changes = {}

    if result == "success":
        template.success_count += 1
        changes["success_count_delta"] = 1
    elif result == "fail":
        template.failure_count += 1
        changes["failure_count_delta"] = 1
    elif result == "partial":
        # 部分成功：不增加失败计数，只降低奖励
        changes["partial"] = True
        reward_delta *= 0.5

    # reward EMA
    prev_ema = template.reward_ema
    template.reward_ema = round(template.reward_ema * 0.9 + reward_delta * 0.1, 4)
    changes["reward_ema_from"] = prev_ema
    changes["reward_ema_to"] = template.reward_ema

    # confidence 更新
    prev_conf = template.confidence
    conf_delta = reward_delta * 0.05
    template.confidence = max(0.0, min(1.0, template.confidence + conf_delta))
    changes["confidence_from"] = prev_conf
    changes["confidence_to"] = template.confidence

    # success_rate 变化
    total = template.success_count + template.failure_count
    if total > 0:
        changes["success_rate"] = round(template.success_count / total, 4)

    return changes


def promote_template(template_id: str) -> dict:
    """将模板从 proposed 提升到 active。"""
    store = get_procedure_store()
    t = store.get_template(template_id)
    if not t:
        return {"ok": False, "reason": "template not found"}
    if t.status not in ("draft", "proposed"):
        return {"ok": False, "reason": f"cannot promote from status {t.status}"}

    prev = t.status
    t.status = "active"
    t.confidence = max(t.confidence, 0.4)
    store.save_template(t)
    logger.info("[procedural.feedback] promoted %s: %s -> active", template_id, prev)
    return {"ok": True, "template_id": template_id, "status": "active", "from": prev}


def retire_template(template_id: str, reason: str = "") -> dict:
    """将模板标记为 deprecated（如果已 deprecated 则移入 archive）。"""
    store = get_procedure_store()
    t = store.get_template(template_id)
    if not t:
        return {"ok": False, "reason": "template not found"}

    if t.status == "deprecated" or reason == "archive":
        # 第二次调用或强制归档 -> 移入 archive
        store.archive_template(t)
        logger.info("[procedural.feedback] archived %s (%s)", template_id, reason)
        return {"ok": True, "template_id": template_id, "status": "archive"}

    prev = t.status
    t.status = "deprecated"
    t.confidence = max(0.0, t.confidence * 0.3)
    store.save_template(t)
    logger.info("[procedural.feedback] deprecated %s: %s -> deprecated", template_id, prev)
    return {"ok": True, "template_id": template_id, "status": "deprecated", "from": prev}


def record_batch_feedback(feedback_list: list[dict]) -> list[dict]:
    """批量记录反馈。"""
    results = []
    for fb in feedback_list:
        res = record_procedure_feedback(
            template_id=fb.get("template_id", ""),
            run_id=fb.get("run_id", ""),
            result=fb.get("result", "unknown"),
            reward_delta=float(fb.get("reward_delta", 0)),
            notes=fb.get("notes", ""),
        )
        results.append(res)
    return results


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
