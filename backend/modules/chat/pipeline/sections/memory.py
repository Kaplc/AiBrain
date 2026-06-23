"""记忆片段 — 把搜索结果作为独立动态块（参考信息）注入"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    pkg = ctx.work_memory.get("package", {})
    if not isinstance(pkg, dict):
        return

    results = pkg.get("results", [])
    if not results:
        return

    lines = [f"• {r.get('text', '')[:200]}" for r in results]
    ctx.add_block("memory_reference", "\n".join(lines), title="参考信息")


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="memory",
        description="长期记忆",
        execute=execute,
        enabled=True,
        required=False,
    )
