"""模式提炼器（T004）

把相似样本聚成动作模板。第一版按以下签名聚类：
  1. 动作签名：action 序列（不包含 wait/sleep）
  2. 活动签名：selected_activity
  3. 模式签名：mode + selected_activity

每个聚类达到 min_support 条后生成 ProcedureTemplate。
"""

import hashlib
import json
import logging
from collections import defaultdict
from typing import Optional

from main_brain.procedural_memory.contracts import (
    ProcedureExample,
    ProcedureTemplate,
)

logger = logging.getLogger("main_brain.procedural.miner")

# 默认阈值
_DEFAULT_MIN_SUPPORT = 3          # 最少样本数
_DEFAULT_MIN_SUCCESS_RATE = 0.7   # 最低成功率
_DEFAULT_MAX_TEMPLATES = 200      # 最大模板数


def mine_procedure_templates(
    examples: list[ProcedureExample],
    *,
    min_support: int = _DEFAULT_MIN_SUPPORT,
    min_success_rate: float = _DEFAULT_MIN_SUCCESS_RATE,
    max_templates: int = _DEFAULT_MAX_TEMPLATES,
    existing_count: int = 0,
) -> list[ProcedureTemplate]:
    """从样本中提炼程序记忆模板。

    Args:
        examples: 归一化后的样本列表。
        min_support: 一个聚类最少需要多少条样本才生成模板。
        min_success_rate: 聚类中成功样本的最低比例。
        max_templates: 模板总数上限（含已有）。
        existing_count: 当前已有的模板数（用于上限判断）。

    Returns:
        新提炼的模板列表。
    """
    if not examples:
        return []

    available = max(0, max_templates - existing_count)
    if available <= 0:
        logger.info("[procedural.miner] template cap reached (%d), skipping", max_templates)
        return []

    # 多维度聚类
    clusters = _cluster_examples(examples)

    templates = []
    for sig, items in clusters.items():
        if len(items) < min_support:
            continue

        success_count = sum(1 for x in items if x.outcome == "success")
        success_rate = success_count / len(items)
        if success_rate < min_success_rate:
            continue

        tpl = _build_template(sig, items)
        templates.append(tpl)

        if len(templates) >= available:
            break

    logger.info(
        "[procedural.miner] mined %d templates from %d examples (%d clusters)",
        len(templates), len(examples), len(clusters),
    )
    return templates


# ── 聚类 ────────────────────────────────────────────────

def _cluster_examples(examples: list[ProcedureExample]) -> dict[str, list[ProcedureExample]]:
    """多维度聚类，返回 dict[signature, examples]"""
    clusters: dict[str, list[ProcedureExample]] = defaultdict(list)

    for ex in examples:
        sig = _build_signature(ex)
        clusters[sig].append(ex)

    return dict(clusters)


def _build_signature(ex: ProcedureExample) -> str:
    """从样本计算签名，用于聚类。

    签名由三部分组成：
      1. mode + selected_activity
      2. 非 wait/sleep 的动作序列哈希
      3. trigger 摘要（tick_type）
    """
    activity = ex.context_digest.get("activity", "")
    mode = ex.mode

    action_sig = _action_sequence_sig(ex.action_sequence)
    tick_type = ex.tick_type

    raw = f"{mode}|{activity}|{action_sig}|{tick_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _action_sequence_sig(action_sequence: list[dict]) -> str:
    """从动作序列生成签名（去掉 wait/sleep 后的精简序列）。"""
    core_actions = [
        a.get("action", "") for a in action_sequence
        if a.get("action", "") not in {"wait", "sleep"}
    ]
    return "->".join(core_actions) if core_actions else "none"


# ── 模板构建 ────────────────────────────────────────────

def _build_template(signature: str, items: list[ProcedureExample]) -> ProcedureTemplate:
    """从一组聚类样本构建一个模板。"""
    activity = items[0].context_digest.get("activity", "procedure")
    mode = items[0].mode

    # 模板 ID
    raw_id = f"proc_{signature}"
    template_id = hashlib.sha256(raw_id.encode()).hexdigest()[:12]

    # 前置条件：从所有样本的公共上下文推断
    preconditions = _infer_preconditions(items)

    # 公共步骤：取样本中频率最高的动作序列
    steps = _extract_common_steps(items)

    # 成功判据
    success_criteria = _infer_success_criteria(items)

    # 风险等级
    risk_level = _infer_risk_level(items, steps)

    # 统计数据
    success_count = sum(1 for x in items if x.outcome == "success")
    failure_count = sum(1 for x in items if x.outcome != "success")
    total = len(items)

    return ProcedureTemplate(
        template_id=template_id,
        name=f"{mode}_{activity}_{signature[:8]}",
        intent=f"{mode} mode 下执行 {activity}",
        trigger_signals={
            "signature": signature,
            "activity": activity,
            "mode": mode,
            "tick_types": list(set(x.tick_type for x in items if x.tick_type)),
        },
        preconditions=preconditions,
        steps=steps,
        success_criteria=success_criteria,
        risk_level=risk_level,
        status="draft",
        confidence=min(0.95, total / 10.0),
        success_count=success_count,
        failure_count=failure_count,
        reward_ema=_reward_ema(items),
        last_mined_at=_now_iso(),
        version=1,
        tags=[mode, activity],
        source_example_ids=[x.example_id for x in items],
        skill_exportable=False,
    )


# ── 推断辅助 ────────────────────────────────────────────

def _infer_preconditions(items: list[ProcedureExample]) -> list[str]:
    """从样本中推断前置条件。

    当前策略：从最少 60% 的样本中共有的上下文特征提取。
    """
    from collections import Counter
    preconditions = []
    n = len(items)
    threshold = max(2, int(n * 0.6))

    # 检查是否有共同的 activity
    activities = Counter(
        x.context_digest.get("activity", "") for x in items
    )
    for act, count in activities.most_common(1):
        if count >= threshold and act:
            preconditions.append(f"activity:{act}")

    # 检查是否有共同的 trigger tick_type
    tick_types = Counter(x.tick_type for x in items if x.tick_type)
    for tt, count in tick_types.most_common(1):
        if count >= threshold:
            preconditions.append(f"tick_type:{tt}")

    return preconditions


def _extract_common_steps(items: list[ProcedureExample]) -> list[dict]:
    """从样本中提取公共动作步骤。

    取频率最高的动作类型序列，给每个步骤附加出现频率。
    """
    from collections import Counter

    # 收集所有非 wait/sleep 动作及其频率
    action_counter: Counter = Counter()
    action_focus_map: dict[str, list[str]] = {}

    for ex in items:
        for a in ex.action_sequence:
            action = a.get("action", "")
            if action in {"wait", "sleep"}:
                continue
            action_counter[action] += 1
            if action not in action_focus_map:
                action_focus_map[action] = []
            focus = a.get("focus", "")
            if focus:
                action_focus_map[action].append(focus)

    n = len(items)
    steps = []
    for action, count in action_counter.most_common():
        # 只在超过 30% 的样本中出现才作为步骤
        if count / n < 0.3:
            continue
        focuses = action_focus_map.get(action, [])
        most_common_focus = ""
        if focuses:
            from collections import Counter as C2
            most_common_focus = C2(focuses).most_common(1)[0][0]

        steps.append({
            "action": action,
            "frequency": round(count / n, 2),
            "typical_focus": most_common_focus,
        })

    return steps


def _infer_success_criteria(items: list[ProcedureExample]) -> list[str]:
    """从成功样本推断判据。"""
    criteria = []
    success_items = [x for x in items if x.outcome == "success"]

    if success_items:
        # 查看成功的常用 stop_reason
        reasons = set(
            x.context_digest.get("stop_reason", "") for x in success_items
        )
        for r in sorted(reasons):
            if r:
                criteria.append(f"stop_reason:{r}")

    if not criteria:
        criteria.append("stop_reason:ready|completed")

    return criteria


def _infer_risk_level(
    items: list[ProcedureExample],
    steps: list[dict],
) -> str:
    """推断风险等级。

    规则：
      - 包含 use_tool 且是 write/delete 类操作 -> high
      - 包含 use_tool -> medium
      - 否则 -> low
    """
    # 检查步骤中是否有高风险动作
    high_risk_actions = {"use_tool", "update_state"}
    found_high = False
    found_medium = False

    for step in steps:
        action = step.get("action", "")
        if action in high_risk_actions:
            found_high = True
        elif action not in {"wait", "sleep", "final_reply"}:
            found_medium = True

    if found_high:
        return "high"
    if found_medium:
        return "medium"
    return "low"


def _reward_ema(items: list[ProcedureExample]) -> float:
    """计算奖励的指数滑动平均（从样本直接估算）。"""
    if not items:
        return 0.0
    ema = 0.0
    alpha = 0.1
    for x in items:
        ema = alpha * x.reward + (1 - alpha) * ema
    return round(ema, 4)


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
