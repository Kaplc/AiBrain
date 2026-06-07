"""记忆片段 — 从工作记忆读取 handle_packagemem 结果"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    pkg_text = ctx.work_memory.get("package", "")
    if not pkg_text:
        return

    # 按 --- 分隔提取各条记忆
    mem_items = [item.strip() for item in pkg_text.split("---") if item.strip()]

    if not mem_items:
        return

    lines = [f"• {item[:200]}" for item in mem_items]
    ctx.add_section("相关记忆", "\n".join(lines))


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="memory",
        description="长期记忆",
        execute=execute,
        enabled=True,
        required=False,
    )
