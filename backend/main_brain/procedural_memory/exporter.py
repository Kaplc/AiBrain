"""Skill 导出草稿器（T010）

将高置信、低风险的稳定模板导出为 skill 草稿 Markdown 文件。
草稿保存在 `.claude/skills/` 附近或指定的草稿目录中，需要人工确认后才注册为正式 skill。

导出条件：
  1. 模板状态为 active
  2. confidence >= 0.6
  3. risk_level 为 low
  4. source_example_ids 不少于 5 条
"""

import datetime
import logging
import os
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate
from main_brain.memory.procedural.store import get_procedure_store

logger = logging.getLogger("main_brain.procedural.exporter")

# 导出门槛
_MIN_CONFIDENCE = 0.6
_MIN_EXAMPLES = 5
_ALLOWED_STATUSES = {"active"}

# 草稿保存目录
_DRAFT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", ".claude", "skills", "drafts",
)


def export_procedure_skill_draft(template_id: str) -> dict:
    """将指定模板导出为 skill 草稿。

    Args:
        template_id: 目标模板 ID。

    Returns:
        {"ok": bool, "skill_path": str, "template_id": str, "reason": str}
    """
    store = get_procedure_store()
    template = store.get_template(template_id)
    if not template:
        return {"ok": False, "reason": "template not found"}

    # 检查导出条件
    checks = _check_export_eligibility(template)
    if not checks["eligible"]:
        return {"ok": False, "reason": checks["reason"], "checks": checks}

    # 生成 skill 草稿
    try:
        skill_md = _build_skill_draft(template)
        skill_path = _save_draft(template, skill_md)

        # 标记可导出
        if not template.skill_exportable:
            template.skill_exportable = True
            store.save_template(template)

        logger.info(
            "[procedural.exporter] exported skill draft: %s -> %s",
            template_id, skill_path,
        )
        return {
            "ok": True,
            "skill_path": skill_path,
            "template_id": template_id,
            "template_name": template.name,
        }
    except Exception as e:
        logger.exception("[procedural.exporter] export failed: %s", e)
        return {"ok": False, "reason": f"export error: {e}"}


def export_eligible_templates() -> list[dict]:
    """批量导出所有符合条件且未导出的模板。"""
    store = get_procedure_store()
    exported = []
    candidates = store.get_templates_by_status("active")
    skipped = 0
    for t in candidates:
        if t.skill_exportable:
            skipped += 1
            continue
        if t.confidence < _MIN_CONFIDENCE:
            skipped += 1
            continue
        if t.risk_level != "low":
            skipped += 1
            continue
        if len(t.source_example_ids) < _MIN_EXAMPLES:
            skipped += 1
            continue

        result = export_procedure_skill_draft(t.template_id)
        if result.get("ok"):
            exported.append(result)
    logger.info("[exporter] batch export: %d exported, %d skipped from %d active templates",
                 len(exported), skipped, len(candidates))
    return exported


def _check_export_eligibility(template: ProcedureTemplate) -> dict:
    """检查模板是否满足导出条件。"""
    issues = []

    if template.status not in _ALLOWED_STATUSES:
        issues.append(f"status must be active, got {template.status}")
    if template.confidence < _MIN_CONFIDENCE:
        issues.append(f"confidence {template.confidence:.2f} < {_MIN_CONFIDENCE}")
    if template.risk_level != "low":
        issues.append(f"risk_level must be low, got {template.risk_level}")
    if len(template.source_example_ids) < _MIN_EXAMPLES:
        issues.append(
            f"source_examples {len(template.source_example_ids)} < {_MIN_EXAMPLES}"
        )

    return {
        "eligible": len(issues) == 0,
        "reason": "; ".join(issues) if issues else "ok",
        "confidence": template.confidence,
        "risk_level": template.risk_level,
        "example_count": len(template.source_example_ids),
    }


def _build_skill_draft(template: ProcedureTemplate) -> str:
    """生成 skill 草稿 Markdown 内容。"""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps_md = "\n".join(
        f"{i+1}. `{s.get('action', '')}` — {s.get('typical_focus', '')}"
        for i, s in enumerate(template.steps)
    )

    return f"""---
name: {template.name}
description: 从程序记忆导出的 skill 草稿 — {template.intent}
status: draft
source: procedural_memory
template_id: {template.template_id}
exported_at: {now}
confidence: {template.confidence}
examples: {len(template.source_example_ids)}
risk: {template.risk_level}
---

# {template.name}

## 说明

自动从程序记忆模板导出的 skill 草稿，需要人工验证后方可发布。

**原始意图**: {template.intent}

## 适用场景

- 模式: {template.trigger_signals.get("mode", "?")}
- 活动: {template.trigger_signals.get("activity", "?")}
- tick 类型: {', '.join(template.trigger_signals.get("tick_types", []))}

## 前置条件

{chr(10).join(f'- {c}' for c in template.preconditions) if template.preconditions else '- 无特殊前置条件'}

## 步骤

{steps_md}

## 成功判据

{chr(10).join(f'- {c}' for c in template.success_criteria) if template.success_criteria else '- 未明确定义'}

## 统计

- 置信度: {template.confidence:.2f}
- 成功次数: {template.success_count}
- 失败次数: {template.failure_count}
- Reward EMA: {template.reward_ema}

## 样本来源

{chr(10).join(f'- {eid}' for eid in template.source_example_ids[:10])}
{'...' if len(template.source_example_ids) > 10 else ''}

## 注意事项

- ⚠️ 这是自动生成的草稿，需要人工审核后才能启用。
- 检查步骤是否完整、安全、可执行。
- 如有不合规、不准确、不安全的内容，请修正或丢弃此草稿。
"""


def _save_draft(template: ProcedureTemplate, content: str) -> str:
    """将草稿写入文件。"""
    os.makedirs(_DRAFT_DIR, exist_ok=True)

    safe_name = template.name.replace(" ", "_").replace("/", "_").lower()
    filename = f"skill_draft_{safe_name}_{template.template_id[:8]}.md"
    filepath = os.path.join(_DRAFT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("[procedural.exporter] draft saved to %s", filepath)
    return filepath
