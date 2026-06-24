"""Expression Bridge — 把大脑产出的回复转成 SSE token 流（T004 / FR-004）

职责：
  - 接收 BrainReplyEnvelope，生成 SSE start/token/usage/done
  - 不参与决策，只是输出层
"""
from __future__ import annotations

import json
import logging
from typing import Iterator

from ..contracts import BrainReplyEnvelope, BrainJudgeDecision, REPLY_TYPE_FALLBACK

logger = logging.getLogger("main_brain.bridge.reply")


def sse_start() -> dict:
    return {"type": "start"}


def sse_token(text: str) -> dict:
    return {"type": "token", "content": text}


def sse_usage(input_tokens: int = 0, output_tokens: int = 0) -> dict:
    return {"type": "usage", "prompt_tokens": input_tokens, "completion_tokens": output_tokens}


def sse_done() -> dict:
    return {"type": "done"}


def sse_error(message: str) -> dict:
    return {"type": "error", "message": message}


def envelope_to_events(envelope: BrainReplyEnvelope) -> Iterator[dict]:
    """把 BrainReplyEnvelope 转成 SSE 事件流。"""
    yield sse_start()
    if envelope.text:
        yield sse_token(envelope.text)
    if envelope.usage:
        yield sse_usage(
            envelope.usage.get("input_tokens", 0),
            envelope.usage.get("output_tokens", 0),
        )
    yield sse_done()


def judge_reply_to_envelope(
    decision: BrainJudgeDecision,
    event_id: str,
    trace_id: str,
) -> BrainReplyEnvelope:
    """从 BrainJudgeDecision 提取最终回复内容。"""
    text = ""
    strategy = decision.reply_strategy or {}
    if isinstance(strategy, dict):
        text = strategy.get("final_reply", "") or strategy.get("text", "") or ""
    if not text:
        text = decision.thought_summary or ""
    return BrainReplyEnvelope(
        trace_id=trace_id,
        source_event_id=event_id,
        text=text,
        reply_type=REPLY_TYPE_FALLBACK if decision.confidence < 0.3 else "final",
        metadata={"confidence": decision.confidence},
    )
