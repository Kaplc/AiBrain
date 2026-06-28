"""Auto-Skill 格式化器 — 将 ProcedureTemplate 渲染为 SKILL.md

纯模板渲染，无需 LLM 调用。输出 YAML frontmatter + Markdown 描述内容。
"""

import datetime
import logging

from main_brain.procedural_memory.contracts import ProcedureTemplate

logger = logging.getLogger("main_brain.auto_skill.formatter")


def format_as_skill_md(template: ProcedureTemplate) -> str:
    """将模板渲染为 SKILL.md 格式。

    Args:
        template: 程序记忆模板。

    Returns:
        SKILL.md 完整文本。
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps_md = "\n".join(
        f"{i+1}. `{s.get('action', '')}` — {s.get('typical_focus', '')}"
        for i, s in enumerate(template.steps)
    )
    trigger = template.trigger_signals or {}
    trigger_mode = trigger.get("mode", "?")
    trigger_activity = trigger.get("activity", "?")
    tick_types = trigger.get("tick_types", [])

    preconditions_md = (
        "\n".join(f"- {c}" for c in template.preconditions)
        if template.preconditions
        else "- 无特殊前置条件"
    )
    criteria_md = (
        "\n".join(f"- {c}" for c in template.success_criteria)
        if template.success_criteria
        else "- 未明确定义"
    )

    return f"""---
name: auto_{template.name}
description: {template.intent}
source: procedural_memory
confidence: {template.confidence}
template_id: {template.template_id}
trigger: {trigger_mode} mode, activity={trigger_activity}
risk: {template.risk_level}
version: {template.version}
deployed_at: {now}
---

# auto_{template.name}

## 触发条件
- mode={trigger_mode}
- activity={trigger_activity}
- tick_type={', '.join(tick_types) if tick_types else '任意'}

## 前置条件
{preconditions_md}

## 执行步骤
{steps_md}

## 成功标准
{criteria_md}

## 统计
- 置信度: {template.confidence:.2f}
- 成功次数: {template.success_count}
- 失败次数: {template.failure_count}
- Reward EMA: {template.reward_ema}
- 样本数: {len(template.source_example_ids)}
"""


def get_skill_filename(template: ProcedureTemplate) -> str:
    """根据模板生成 SKILL.md 文件名。"""
    safe_name = template.name.replace(" ", "_").replace("/", "_").lower()
    return f"auto_{safe_name}_{template.template_id[:8]}.md"
