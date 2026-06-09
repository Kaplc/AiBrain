"""潜意识片段 — 定义 AI 的核心身份与行为准则"""
from ..context import PromptContext

PRIORITY_RULE = "\n\n【重要】请始终优先使用当前对话上下文来理解用户意图。只有在当前对话中找不到相关信息时，才参考下面的记忆内容。"


def execute(ctx: PromptContext) -> None:
    parts = []
    if ctx.system_persona:
        parts.append(ctx.system_persona)
    parts.append(PRIORITY_RULE)
    ctx.add_section("潜意识", "\n".join(parts))


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="subconscious",
        description="潜意识设定",
        execute=execute,
        enabled=True,
        required=False,
    )
