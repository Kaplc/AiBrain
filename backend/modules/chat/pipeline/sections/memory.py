"""记忆片段 — 把搜索结果放到 metadata 供 loop 作为独立参考消息"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    pkg = ctx.work_memory.get("package", {})
    if not isinstance(pkg, dict):
        return

    results = pkg.get("results", [])
    if not results:
        return

    lines = [f"• {r.get('text', '')[:200]}" for r in results]
    ctx.metadata["_memory_reference"] = "\n".join(lines)


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="memory",
        description="长期记忆",
        execute=execute,
        enabled=True,
        required=False,
    )
