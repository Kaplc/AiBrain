"""brain_context section — 把 Reactive BrainSession 的内部思考注入 prompt（T012）

当 brain_session_enabled 且本次回复前跑了 reactive session 时，ChatManager 会持有
latest brain_context（reply_strategy + thoughts）。本节把它拼成【内部思考】一段，
让回复体现「先想了再答」。为空或关闭时无任何输出，完全兼容旧链路（plan FR-013）。

全包 try/except 静默降级，绝不阻断对话。
"""
from ..context import PromptContext


def _latest_brain_context() -> dict:
    """从 ChatManager 取最近一次 reactive session 的 brain_context。"""
    try:
        from modules.chat import ChatManager
        return getattr(ChatManager.get_instance(), "_brain_context", {}) or {}
    except Exception:
        return {}


def execute(ctx: PromptContext) -> None:
    try:
        from main_brain.config import get_brain_config
        if not get_brain_config().session_enabled:
            return
        bc = _latest_brain_context()
        if not bc or not bc.get("thoughts"):
            return

        lines = []
        strategy = bc.get("reply_strategy", {}) or {}
        if strategy.get("tone"):
            lines.append(f"（回复语气倾向：{strategy['tone']}）")
        for t in bc.get("thoughts", [])[:3]:
            focus = t.get("focus", "")
            summary = t.get("summary", "")
            if summary:
                lines.append(f"• {focus + '：' if focus else ''}{summary}")
        if strategy.get("should_mention_thoughts") and strategy.get("key_points"):
            kp = "、".join(str(k) for k in strategy["key_points"][:3])
            lines.append(f"（可自然带出：{kp}）")

        if lines:
            ctx.add_section("内部思考", "\n".join(lines))
    except Exception:
        pass


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="brain_context",
        description="BrainSession 内部思考注入",
        execute=execute,
        enabled=True,
        required=False,
    )
