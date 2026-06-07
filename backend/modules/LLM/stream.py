"""
LLM 流式调用 - 统一 provider 分发

call_llm_stream() 是本模块的入口函数，对外 yield 统一格式：
    {"content": str, "usage": dict | None, "finish_reason": str | None}

支持的 provider：
- OpenAI 兼容：openai / deepseek / groq / ollama / lmstudio / together / minimax
  全部走 openai SDK（只需 base_url 区分）
- Anthropic：anthropic SDK，解析 content_block_delta

错误处理：底层 SDK 抛错向上层抛出；单 chunk 解析失败不中断流（continue）。
"""
from __future__ import annotations
import json
import logging
import re
from typing import Iterator, Optional

from .config import LLMConfig

logger = logging.getLogger(__name__)


# ── Provider 路由表 ─────────────────────────────────────────
# 哪些 provider 走 OpenAI 兼容协议（base_url 不同），哪些走原生 SDK
_OPENAI_COMPATIBLE = {
    "openai", "deepseek", "groq", "ollama", "lmstudio", "together", "minimax",
}


# ── 公开 API ───────────────────────────────────────────────
def call_llm_stream(
    system_prompt: str = "",
    user_prompt: str = "",
    config: LLMConfig = None,
    messages: list[dict] = None,
) -> Iterator[dict]:
    """流式调用 LLM，统一 yield。

    两种调用方式：
    1. 传入 system_prompt + user_prompt → 自动构造 messages
    2. 传入 messages → 直接使用，忽略 system_prompt 和 user_prompt

    Yields:
        {"content": str, "usage": dict|None, "finish_reason": str|None}

    Raises:
        ValueError: 不支持的 provider
        RuntimeError: API 调用失败
    """
    ok, err = config.validate()
    if not ok:
        raise ValueError(f"invalid LLMConfig: {err}")

    provider = config.provider
    if provider in _OPENAI_COMPATIBLE:
        yield from _openai_compatible_stream(system_prompt, user_prompt, config, messages)
    elif provider == "anthropic":
        yield from _anthropic_stream(system_prompt, user_prompt, config, messages)
    else:
        raise ValueError(f"unsupported provider: {provider}")


def call_llm_sync(
    system_prompt: str,
    user_prompt: str,
    config: LLMConfig,
) -> str:
    """非流式调用：把流拼起来。给不需要流的地方用（单元测试、批处理）。"""
    parts = []
    for chunk in call_llm_stream(system_prompt, user_prompt, config):
        if chunk.get("content"):
            parts.append(chunk["content"])
    return "".join(parts)


# ── OpenAI 兼容协议 ─────────────────────────────────────────
def _openai_compatible_stream(
    system_prompt: str = "",
    user_prompt: str = "",
    config: LLMConfig = None,
    messages: list[dict] = None,
) -> Iterator[dict]:
    """OpenAI 兼容协议：所有 chunk 都有 .choices[0].delta.content"""
    try:
        import openai
    except ImportError as e:
        raise RuntimeError("openai SDK 未安装，请 `pip install openai`") from e

    kwargs = {"api_key": config.api_key or "dummy"}
    if config.base_url:
        kwargs["base_url"] = config.base_url

    client = openai.OpenAI(**kwargs)

    # 优先使用传入的 messages，否则自动构造
    if messages is not None:
        msgs = messages
    else:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        if user_prompt:
            msgs.append({"role": "user", "content": user_prompt})

    # DeepSeek 思考模式
    extra_kwargs = {}
    if config.provider == "deepseek" and config.thinking_mode:
        extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

    try:
        stream = client.chat.completions.create(
            model=config.model,
            messages=msgs,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            stream=True,
            stream_options={"include_usage": True},
            **extra_kwargs,
        )
    except Exception as e:
        raise RuntimeError(f"OpenAI 兼容调用失败 ({config.provider}/{config.model}): {e}") from e

    for chunk in stream:
        try:
            content = ""
            finish_reason = None
            usage = None

            if getattr(chunk, "choices", None) and chunk.choices:
                choice = chunk.choices[0]
                if choice.delta and choice.delta.content:
                    content = choice.delta.content
                finish_reason = choice.finish_reason

            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }

            if content or usage or finish_reason:
                yield {"content": content, "usage": usage, "finish_reason": finish_reason}
        except (AttributeError, IndexError) as e:
            # 单 chunk 解析失败不中断流
            logger.warning(f"[llm:stream] chunk 解析失败: {e} | chunk={chunk!r}")
            continue


# ── Anthropic 协议 ─────────────────────────────────────────
def _anthropic_stream(
    system_prompt: str = "",
    user_prompt: str = "",
    config: LLMConfig = None,
    messages: list[dict] = None,
) -> Iterator[dict]:
    """Anthropic 流式：event stream 含 typed event；
    usage 在 message_delta 事件里。

    失败时 raise RuntimeError（v1 简单实现）。
    """
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK 未安装，请 `pip install anthropic`") from e

    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = anthropic.Anthropic(**kwargs)

    messages = []
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})

    try:
        with client.messages.stream(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system=system_prompt or "",
            messages=msgs,
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield {"content": text, "usage": None, "finish_reason": None}

            # 流结束后从 final_message 取 usage
            try:
                final = stream.get_final_message()
                if final and final.usage:
                    usage = {
                        "prompt_tokens": final.usage.input_tokens,
                        "completion_tokens": final.usage.output_tokens,
                    }
                    yield {"content": "", "usage": usage, "finish_reason": final.stop_reason}
            except Exception as e:
                logger.warning(f"[llm:anthropic] 取 final_usage 失败: {e}")
    except Exception as e:
        raise RuntimeError(f"Anthropic 调用失败 ({config.model}): {e}") from e


# ── 测试钩子（让单元测试可以 mock provider） ───────────────────
def _is_openai_compatible(provider: str) -> bool:
    return provider in _OPENAI_COMPATIBLE
