"""main_brain.adapters — 包装现有能力边界（plan 第六节决策 #4）

adapter 只包装，不复制 memory/state/tool/expression manager。每个 adapter 提供一个
handle(decision, ctx, dry_run) 满足 action_handler 约定，并暴露便捷方法供 session /
daemon 直接调用。

build_action_handlers() 把 next_action → adapter 映射装配成 controller 可用的注册表。
"""
from __future__ import annotations

from typing import Callable

from ..contracts import BrainJudgeDecision, BrainRunContext

ActionHandler = Callable[[BrainJudgeDecision, BrainRunContext, bool], dict]


def build_action_handlers() -> dict[str, ActionHandler]:
    """装配 next_action → adapter handler 注册表（延迟构造单例 adapter）。"""
    from .memory import get_memory_adapter
    from .state import get_state_adapter
    from .expression import get_expression_adapter
    from .tools import get_tool_adapter
    from .learning import get_learning_adapter

    mem = get_memory_adapter()
    st = get_state_adapter()
    exp = get_expression_adapter()
    tools = get_tool_adapter()
    learn = get_learning_adapter()

    return {
        "recall_memory": mem.handle_recall,
        "update_state": st.handle_update_state,
        "create_pending": exp.handle_create_pending,
        "use_tool": tools.handle_use_tool,
        "final_reply": learn.handle_final_reply,   # 落 reply_strategy（hints 由 caller 沉淀）
    }


__all__ = ["build_action_handlers", "ActionHandler"]
