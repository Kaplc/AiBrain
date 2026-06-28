"""Auto-Skill 自动技能部署系统

程序记忆挖出高置信度行为模板 → 格式化为标准 SKILL.md → 写入
data/auto_skills/ → Judge 的 procedure_matches 直接加载注入 → LLM
决策时自然参考经验。不再生成 Python 代码，不碰 ToolRegistry。

公共 API：
    sync_all          — 扫描所有 active 模板 → 部署/更新/撤回 SKILL.md
    list_deployed     — 列出已部署的所有自动技能
    load_skill_md     — 按 template_id 加载 SKILL.md 全文
    check_and_rollback — 检查单模板是否需要回滚
"""

from main_brain.auto_skill.deployer import deploy_skill, undeploy_skill, list_deployed
from main_brain.auto_skill.rollback import check_and_rollback, rollback_by_template_id
from main_brain.auto_skill.judge_hook import load_skill_md, format_skills_for_prompt

__all__ = [
    "sync_all",
    "list_deployed",
    "load_skill_md",
    "format_skills_for_prompt",
    "deploy_skill",
    "undeploy_skill",
    "check_and_rollback",
    "rollback_by_template_id",
]


# 部署阈值（与 exporter.py 的 _MIN_CONFIDENCE/_MIN_EXAMPLES/_ALLOWED_STATUSES 保持一致）
_DEPLOY_CONFIDENCE = 0.6
_DEPLOY_EXAMPLES = 5
_DEPLOY_STATUSES = {"active"}
# 回滚阈值（与 rollback.py 的 _RETIRE_CONFIDENCE/_RETIRE_STATUSES 保持一致）
_RETIRE_STATUSES = {"deprecated", "archive", "cooling"}
_RETIRE_CONFIDENCE = 0.5


def sync_all() -> dict:
    """扫描所有 active 模板 → 部署/更新/撤回 SKILL.md。

    在 procedural_memory.scheduler.run_mining() 之后自动调用。

    Returns:
        {"deployed": list, "removed": list, "errors": list}
    """
    from main_brain.memory.procedural.store import get_procedure_store

    store = get_procedure_store()
    templates = store.get_all_templates()

    deployed = []
    removed = []
    errors = []

    for t in templates:
        try:
            # 检查是否应回滚
            if t.status in _RETIRE_STATUSES or t.confidence < _RETIRE_CONFIDENCE:
                result = check_and_rollback(t)
                if result.get("rolled_back"):
                    removed.append({
                        "template_id": t.template_id,
                        "name": t.name,
                        "reason": result.get("reason", ""),
                    })
                continue

            # 检查是否应部署（首次部署或更新）
            if (t.status in _DEPLOY_STATUSES
                    and t.confidence >= _DEPLOY_CONFIDENCE
                    and t.risk_level == "low"
                    and len(t.source_example_ids) >= _DEPLOY_EXAMPLES):
                result = deploy_skill(t)
                if result.get("ok"):
                    deployed.append(result)
                    if not t.skill_exportable:
                        t.skill_exportable = True
                        store.save_template(t)

        except Exception as e:
            logger = __import__("logging").getLogger("main_brain.auto_skill")
            logger.exception("[auto_skill] sync error for %s: %s", t.template_id, e)
            errors.append({"template_id": t.template_id, "error": str(e)})

    if deployed or removed:
        logger = __import__("logging").getLogger("main_brain.auto_skill")
        logger.info(
            "[auto_skill] sync: %d deployed, %d removed",
            len(deployed), len(removed),
        )

    return {
        "deployed": deployed,
        "removed": removed,
        "errors": errors,
    }
