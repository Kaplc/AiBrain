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
        _bc = get_brain_config()
        # brain-first 模式或 session_enabled 任一为真时注入
        if not (_bc.get_chat_mode() == _bc.CHAT_MODE_BRAIN_FIRST or _bc.session_enabled):
            return

        lines = []

        # 1. BrainSession 内部思考
        bc = _latest_brain_context()
        if bc and bc.get("thoughts"):
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

        # 2. T007: 当前 trace 事件链（只取本链路事件，不混入旧事件）
        try:
            from modules.chat import ChatManager as _CM
            _trace_id, _ = _CM.get_instance().get_event_trace()
            if _trace_id:
                from main_brain.logging.event_log import get_event_log
                elog = get_event_log()
                chain = elog.get_event_chain(_trace_id)
                if chain:
                    ev_lines = []
                    for e in chain[-4:]:
                        src = e.get("source", "?")
                        content = (e.get("content") or "")[:80]
                        if content:
                            ev_lines.append(f"  [{src}] {content}")
                    if ev_lines:
                        lines.append("\n当前事件链：\n" + "\n".join(ev_lines))
        except Exception:
            pass

        if lines:
            ctx.add_block("brain_context", "\n".join(lines), title="内部思考与事件")
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
