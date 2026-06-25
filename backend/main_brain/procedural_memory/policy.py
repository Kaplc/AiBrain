"""主脑集成点（T008）

负责任务调用链路中插入程序记忆的匹配和参考：
  1. TickInput 构建阶段：注入 procedural_matches 到上下文
  2. LifeLoopDaemon.run_tick：在 ActivitySelector 之后、controller 之前匹配
  3. BrainJudge 参考：judge 上下文的 procedure_matches 字段

设计原则：
  - 所有异常 try/except，失败不阻塞主流程
  - dry_run 模式下仍然运行匹配但标记为预览
"""

import logging

from main_brain.procedural_memory.matcher import match_procedure_templates
from main_brain.memory.procedural.store import get_procedure_store

logger = logging.getLogger("main_brain.procedural.policy")


def enrich_tick_context_with_procedures(
    context: dict,
    *,
    top_k: int = 3,
    dry_run: bool = False,
) -> dict:
    """向上下文注入程序记忆匹配结果（原地修改 context）。

    Args:
        context: 当前上下文 dict（含 mode, tick_type, activity 等）。
        top_k: 最大匹配数。
        dry_run: 预览模式（注入结果标记 preview）。

    Returns:
        添加了 procedure_matches 字段的 context（调用者可忽略返回值）。
    """
    try:
        store = get_procedure_store()
        templates = store.get_templates_by_status("proposed", "active", "cooling")
        if not templates:
            context["procedure_matches"] = []
            return context

        match_context = _build_match_context(context)
        matches = match_procedure_templates(
            match_context,
            templates=templates,
            top_k=top_k,
        )

        if dry_run:
            for m in matches:
                m["_preview"] = True

        context["procedure_matches"] = matches

        if matches:
            logger.debug(
                "[procedural.policy] %d match(es) for context "
                "(activity=%s, mode=%s, tick=%s)",
                len(matches),
                context.get("selected_activity", context.get("activity", "?")),
                context.get("mode", "?"),
                context.get("tick_type", "?"),
            )

    except Exception as e:
        logger.warning("[procedural.policy] enrich failed: %s", e)
        context["procedure_matches"] = []

    return context


def _build_match_context(source: dict) -> dict:
    """从运行上下文中提取匹配器所需的关键特征。"""
    return {
        "mode": source.get("mode", ""),
        "tick_type": source.get("tick_type", ""),
        "activity": source.get("selected_activity", source.get("activity", "")),
        "actions": source.get("actions", []),
        "open_loops": source.get("open_loops", source.get("life_state", {}).get("open_loops", [])),
        "goals": source.get("goals", source.get("life_state", {}).get("goals", [])),
    }


def format_procedure_matches_for_prompt(matches: list[dict]) -> str:
    """将程序记忆匹配结果格式化为给 judge 的提示文本。

    格式：每条匹配包含 template_id、score、reason 和前几步预览。
    """
    if not matches:
        return ""

    lines = ["", "【程序记忆参考】以下已有经验模板匹配当前上下文："]
    for i, m in enumerate(matches, 1):
        steps = " → ".join(m.get("step_preview", []))
        lines.append(
            f"  {i}. [{m['template_id']}] 适配度={m['score']} | "
            f"{m['reason']} | 步骤: {steps or '无'}"
        )
    lines.append("你可以参考这些经验，但不必严格遵守。")
    return "\n".join(lines)
