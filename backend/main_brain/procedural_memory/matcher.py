"""上下文匹配器与评分器（T006）

在当前上下文中匹配最适合的程序记忆模板，输出 top-k ProcedureMatch。

评分维度：
  1. context_fit: 上下文中包含 trigger_signals 的程度
  2. success_fit: 模板的历史成功率
  3. risk_penalty: 高风险模板匹配时降低分数
  4. final_score: context_fit * success_fit - risk_penalty
"""

import logging
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate, ProcedureMatch
from modules.brain.memory.procedural.store import get_procedure_store
from modules.brain.memory.procedural.index import ProcedureIndex

logger = logging.getLogger("main_brain.procedural.matcher")


def match_procedure_templates(
    context: dict,
    templates: Optional[list[ProcedureTemplate]] = None,
    *,
    top_k: int = 3,
    min_score: float = 0.1,
) -> list[dict]:
    """在当前上下文中匹配程序记忆模板。

    Args:
        context: 当前上下文 dict（需包含 mode, tick_type, activity, open_loops, goals 等）。
        templates: 显式传入模板列表（None 时自动从 store 加载）。
        top_k: 返回的最大匹配数。
        min_score: 最低匹配分数过滤。

    Returns:
        按分数降序排列的 match dict 列表（可直接注入上下文）。
    """
    if templates is None:
        store = get_procedure_store()
        templates = store.get_templates_by_status("proposed", "active", "cooling")
    else:
        # 显式传入时也过滤可用状态
        templates = [t for t in templates if t.status in ("proposed", "active", "cooling")]

    if not templates:
        logger.debug("[matcher] no templates available for context (mode=%s, activity=%s)",
                      context.get("mode"), context.get("activity"))
        return []

    logger.debug("[matcher] matching %d templates against context (mode=%s, activity=%s, tick=%s)",
                  len(templates), context.get("mode"), context.get("activity"), context.get("tick_type"))

    scored = []
    for t in templates:
        # 前置条件检查
        if not _preconditions_met(t, context):
            continue

        score, details = _score_template(t, context)
        if score < min_score:
            continue

        scored.append({
            "template_id": t.template_id,
            "score": round(score, 3),
            "context_fit": round(details.get("context_fit", 0), 3),
            "success_fit": round(details.get("success_fit", 0), 3),
            "risk_penalty": round(details.get("risk_penalty", 0), 3),
            "reason": _match_reason(t, details),
            "step_preview": [s.get("action", "") for s in t.steps[:5]],
            "action_hint": t.intent,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_k]
    if top:
        logger.info("[matcher] top %d/%d: %s",
                      len(top), len(scored),
                      ", ".join(f"{m['template_id']}={m['score']:.2f}" for m in top))
    return top


def _preconditions_met(template: ProcedureTemplate, context: dict) -> bool:
    """检查当前上下文是否满足模板前置条件。"""
    preconditions = template.preconditions
    if not preconditions:
        return True

    for cond in preconditions:
        # 格式: "activity:xxx" 或 "tick_type:xxx"
        if ":" not in cond:
            continue
        key, value = cond.split(":", 1)
        actual = context.get(key)
        if actual is None:
            # 尝试从 context 嵌套字段获取
            actual = _nested_get(context, key)
        if actual != value and actual is not None:
            return False

    return True


def _nested_get(d: dict, key: str, default=None):
    """从嵌套 dict 中取值，支持点号路径。"""
    parts = key.split(".")
    current = d
    for p in parts:
        if isinstance(current, dict):
            current = current.get(p)
        else:
            return default
    return current if current is not None else default


def _score_template(template: ProcedureTemplate, context: dict) -> tuple[float, dict]:
    """计算模板与上下文的匹配分数。

    Score = context_fit * success_fit - risk_penalty

    context_fit (0~1): 上下文特征与模板 trigger_signals 的匹配度
    success_fit (0~1): 模板历史成功率（含 confidence 加权）
    risk_penalty (0~0.5): 高风险模板的自然惩罚
    """
    # 1. 上下文适配度
    context_fit = _compute_context_fit(template, context)

    if context_fit <= 0:
        return 0.0, {"context_fit": 0, "success_fit": 0, "risk_penalty": 0}

    # 2. 历史成功度（受状态修正：active=1x, proposed=0.8x, cooling=0.4x）
    success_fit = _compute_success_fit(template)
    success_fit = _apply_status_modifier(template, success_fit)

    # 3. 风险惩罚
    risk_penalty = _compute_risk_penalty(template)

    # 4. 综合分
    score = context_fit * success_fit - risk_penalty
    score = max(0.0, score)

    return score, {
        "context_fit": context_fit,
        "success_fit": success_fit,
        "risk_penalty": risk_penalty,
        "confidence": template.confidence,
        "success_rate": _success_rate(template),
    }


def _compute_context_fit(template: ProcedureTemplate, context: dict) -> float:
    """计算上下文适配度。"""
    signals = template.trigger_signals
    matches = 0
    total = 0

    # 检查 mode
    mode = context.get("mode", "")
    signal_mode = signals.get("mode", "")
    if signal_mode:
        total += 1
        if mode == signal_mode:
            matches += 1

    # 检查 activity
    activity = context.get("activity", context.get("selected_activity", ""))
    signal_activity = signals.get("activity", "")
    if signal_activity:
        total += 1
        if activity == signal_activity:
            matches += 1

    # 检查 tick_type
    tick_type = context.get("tick_type", "")
    signal_types = signals.get("tick_types", [])
    if signal_types:
        total += 1
        if tick_type in signal_types:
            matches += 1

    # 检查动作签名
    context_actions = context.get("actions", [])
    signal_sig = signals.get("signature", "")
    if signal_sig and context_actions:
        total += 1
        # 粗略匹配：看上下文中是否包含模板的典型动作
        template_steps = [s.get("action", "") for s in template.steps]
        common = set(context_actions) & set(template_steps)
        if common:
            matches += min(len(common) / max(len(template_steps), 1), 1.0)

    # 检查 open_loops 和 goals（如果有）
    open_loops = context.get("open_loops", []) or []
    if open_loops and template.tags:
        total += 1
        # 看 open loop 的内容是否匹配模板的意图
        loop_texts = " ".join(
            [str(l.get("content", l)) for l in open_loops[:3]]
        ).lower()
        if any(tag.lower() in loop_texts for tag in template.tags):
            matches += 1

    if total == 0:
        # 没有可匹配的信号时，给一个基础分
        return 0.3

    return matches / total


def _compute_success_fit(template: ProcedureTemplate) -> float:
    """计算历史成功度。"""
    rate = _success_rate(template)
    # confidence 作为权重
    weighted = rate * (0.5 + 0.5 * template.confidence)
    return max(0.0, min(1.0, weighted))


def _success_rate(template: ProcedureTemplate) -> float:
    total = template.success_count + template.failure_count
    if total == 0:
        return 0.5  # 无历史数据时中性值
    return template.success_count / total


def _apply_status_modifier(template: ProcedureTemplate, success_fit: float) -> float:
    """根据模板状态调整分数。"""
    modifier = {
        "active": 1.0,
        "proposed": 0.8,
        "cooling": 0.4,
        "draft": 0.3,
        "deprecated": 0.0,
        "archive": 0.0,
    }
    return success_fit * modifier.get(template.status, 0.0)


def _compute_risk_penalty(template: ProcedureTemplate) -> float:
    """计算风险惩罚。"""
    penalties = {"low": 0.0, "medium": 0.15, "high": 0.4}
    return penalties.get(template.risk_level, 0.0)


def _match_reason(template: ProcedureTemplate, details: dict) -> str:
    """生成人类可读的匹配原因。"""
    parts = []
    cf = details.get("context_fit", 0)
    sf = details.get("success_fit", 0)

    if cf >= 0.7:
        parts.append("上下文高度匹配")
    elif cf >= 0.4:
        parts.append("上下文部分匹配")

    if sf >= 0.7:
        parts.append("历史成功率高")
    elif sf >= 0.4:
        parts.append("历史记录中性")

    risk_pen = details.get("risk_penalty", 0)
    if risk_pen > 0.3:
        parts.append("含高风险操作")
    elif risk_pen > 0.1:
        parts.append("中等风险")

    if template.status == "active":
        parts.append("活跃模板")
    elif template.status == "proposed":
        parts.append("建议模板")

    return "，".join(parts) if parts else "基础匹配"
