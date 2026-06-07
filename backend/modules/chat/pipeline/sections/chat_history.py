"""对话记录片段 — 从工作记忆读取近期输入"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    entries = ctx.work_memory.get("input", [])
    if not entries:
        return

    lines = []
    for entry in entries[:-1][-5:]:
        lines.append(f"用户：{entry['content']}")

    if lines:
        ctx.add_section("历史对话", "\n".join(lines))


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="chat_history",
        description="对话记录",
        execute=execute,
        enabled=True,
        required=False,
    )
