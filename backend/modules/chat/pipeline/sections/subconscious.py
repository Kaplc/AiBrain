"""潜意识片段 — 定义 AI 的核心身份与行为准则（稳定主前缀）

这是唯一的稳定块：persona + 固定优先规则。只要规则配置不改，连续多轮对话中
该块文本保持字节一致，从而让 [stable system] + [历史] 前缀稳定，提升 KV cache 命中。
"""
from ..context import PromptContext

PRIORITY_RULE = "\n\n【重要】请始终优先使用当前对话上下文来理解用户意图。只有在当前对话中找不到相关信息时，才参考下面的记忆内容。"


def execute(ctx: PromptContext) -> None:
    parts = []
    if ctx.system_persona:
        parts.append(ctx.system_persona)
    parts.append(PRIORITY_RULE)
    ctx.add_stable("subconscious", "\n".join(parts), title="潜意识")


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="subconscious",
        description="潜意识设定",
        execute=execute,
        enabled=True,
        required=False,
    )
