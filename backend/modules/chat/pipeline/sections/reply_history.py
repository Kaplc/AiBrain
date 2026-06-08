"""回复记录片段 — 从工作记忆读取近期 LLM 回复"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    entries = ctx.work_memory.get("output", [])
    if not entries:
        return

    lines = []
    for entry in entries[-5:]:
        content = entry.get("content", "")
        if content:
            # 截断过长的回复（保留前 200 字）
            display = content[:200] + "..." if len(content) > 200 else content
            lines.append(f"助手：{display}")

    if lines:
        ctx.add_section("近期回复", "\n".join(lines))


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="reply_history",
        description="近期回复记录",
        execute=execute,
        enabled=True,
        required=False,
    )
