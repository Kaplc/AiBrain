"""当前消息片段 — 用户本次输入"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    if ctx.user_message:
        ctx.add_section("当前对话", ctx.user_message)


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="current_msg",
        description="当前用户消息",
        execute=execute,
        enabled=True,
        required=False,
    )
