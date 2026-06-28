"""Auto-Skill 回滚器 — 置信度降级时自动撤回 SKILL.md

与 procedural_memory/feedback.py 联动：
  - 模板 confidence < 0.5 → 删除对应 SKILL.md
  - 模板 status → deprecated/archive/cooling → 删除对应 SKILL.md
  - 模板 source_example_ids 被清空 → 删除对应 SKILL.md
"""

import logging
import os
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate

logger = logging.getLogger("main_brain.auto_skill.rollback")

# 回滚阈值
_RETIRE_CONFIDENCE = 0.5
_RETIRE_STATUSES = {"deprecated", "archive", "cooling"}
_MIN_SOURCE_EXAMPLES = 1


def check_and_rollback(template: ProcedureTemplate) -> dict:
    """检查模板是否应触发回滚，如果是则删除对应 SKILL.md。

    Args:
        template: 可能已降级的模板。

    Returns:
        {"rolled_back": bool, "reason": str, "template_id": str}
    """
    # 检查条件
    if template.status in _RETIRE_STATUSES:
        return _do_rollback(template, f"status={template.status}")

    if template.confidence < _RETIRE_CONFIDENCE:
        return _do_rollback(
            template,
            f"confidence {template.confidence:.2f} < {_RETIRE_CONFIDENCE}",
        )

    if len(template.source_example_ids) < _MIN_SOURCE_EXAMPLES:
        return _do_rollback(
            template,
            f"source_examples cleared ({len(template.source_example_ids)})",
        )

    return {
        "rolled_back": False,
        "template_id": template.template_id,
        "reason": "",
    }


def rollback_by_template_id(template_id: str) -> dict:
    """按 template_id 回滚（删除对应 SKILL.md）。

    由外部（feedback.py）在置信度更新后调用。

    Args:
        template_id: 模板 ID。

    Returns:
        {"rolled_back": bool, "reason": str, "template_id": str}
    """
    from main_brain.memory.procedural.store import get_procedure_store
    from main_brain.auto_skill.deployer import get_skill_path, undeploy_skill

    store = get_procedure_store()
    template = store.get_template(template_id)
    if not template:
        # 模板已不存在 → 尝试按 ID 查找文件并清理
        skill_path = get_skill_path(template_id)
        if skill_path:
            undeploy_skill(os.path.basename(skill_path))
            logger.info("[auto_skill.rollback] cleaned orphan skill: %s", template_id)
            return {"rolled_back": True, "template_id": template_id, "reason": "orphan cleaned"}
        return {"rolled_back": False, "template_id": template_id, "reason": "template not found"}

    return check_and_rollback(template)


def _do_rollback(template: ProcedureTemplate, reason: str) -> dict:
    """执行回滚：删除 SKILL.md。"""
    from main_brain.auto_skill.deployer import undeploy_skill

    skill_name = f"auto_{template.name}"
    deleted = undeploy_skill(skill_name)
    if deleted:
        logger.info(
            "[auto_skill.rollback] rolled back %s (%s): %s",
            template.template_id, skill_name, reason,
        )
    return {
        "rolled_back": deleted,
        "template_id": template.template_id,
        "reason": reason,
    }
