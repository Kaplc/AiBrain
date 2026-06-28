"""Reactive BrainSession

用户消息触发：通过 autonomous_mind 意识流路径处理，不再经过旧的 controller/judge 流水线。
AI 自主决定如何回应，输出 speak 时 action_detail 即为回复内容。

失败必须降级：任何异常都不影响现有 chat SSE。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("main_brain.session")


class BrainSession:
    """消息入队中转站 —— 不调 tick，只把消息放队列等 alive tick 处理。"""

    def run_reactive(self, user_msg: str, **_) -> dict:
        """用户消息入队，交给 alive tick 处理。不再同步调 tick。"""
        try:
            from .autonomous_mind import get_autonomous_mind
            get_autonomous_mind().handle_user_message(user_msg)
        except Exception as e:
            logger.warning(f"[session] queue message failed: {e}")

        import hashlib, time
        rid = f"msg_{int(time.time())}_{hashlib.md5(user_msg.encode()).hexdigest()[:4]}"
        return {
            "ok": True,
            "run_id": rid,
            "stop_reason": "queued",
            "cycle_count": 0,
            "reply_strategy": {},
            "actions": [],
            "errors": [],
            "thoughts": [],
        }


def _now() -> str:
    from main_brain import clock as times
    return times.now_iso()
