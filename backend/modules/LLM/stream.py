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
    source: str = 'chat',
) -> Iterator[dict]:
    """流式调用 LLM，统一 yield。

    两种调用方式：
    1. 传入 system_prompt + user_prompt → 自动构造 messages
    2. 传入 messages → 直接使用，忽略 system_prompt 和 user_prompt

    Args:
        source: 调用来源标识（'chat' / 'idle_thought'），用于 token_usage 记录

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
        yield from _openai_compatible_stream(system_prompt, user_prompt, config, messages, source)
    elif provider == "anthropic":
        yield from _anthropic_stream(system_prompt, user_prompt, config, messages, source)
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
    source: str = 'chat',
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
                # 提取缓存命中信息（DeepSeek 等返回 prompt_cache_hit_tokens）
                cache_detail = getattr(chunk.usage, 'prompt_cache_hit_tokens', None)
                cache_miss = getattr(chunk.usage, 'prompt_cache_miss_tokens', None)
                if cache_detail is not None:
                    usage["cache_hit_tokens"] = cache_detail
                if cache_miss is not None:
                    usage["cache_miss_tokens"] = cache_miss

                # 记录到数据库
                _record_token_usage(usage, config.model, source)

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
    source: str = 'chat',
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


# ── 非流式调用（Tool Loop 用） ──────────────────────────────

def call_llm_nonstream(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    source: str = 'chat',
) -> dict:
    """非流式 LLM 调用，支持 function calling。

    Args:
        config: LLM 配置
        messages: 消息列表（含 system / user / assistant / tool 角色）
        tools: OpenAI function calling 格式的工具 schema 列表
        tool_choice: "auto" / "none" / {"type":"function","name":"..."} / None
        source: 来源标识（用于 token_usage 记录）

    Returns:
        {
            "content": str | None,
            "tool_calls": list[dict] | None,  # OpenAI 格式
            "usage": dict | None,
            "finish_reason": str | None,       # "stop" | "tool_calls"
        }
    """
    ok, err = config.validate()
    if not ok:
        raise ValueError(f"invalid LLMConfig: {err}")

    provider = config.provider
    if provider in _OPENAI_COMPATIBLE:
        return _openai_compatible_nonstream(config, messages, tools, tool_choice, source)
    elif provider == "anthropic":
        return _anthropic_nonstream(config, messages, tools, tool_choice, source)
    else:
        raise ValueError(f"unsupported provider: {provider}")


def _openai_compatible_nonstream(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    source: str = 'chat',
) -> dict:
    """OpenAI 兼容协议的非流式调用"""
    try:
        import openai
    except ImportError as e:
        raise RuntimeError("openai SDK 未安装") from e

    kwargs = {"api_key": config.api_key or "dummy"}
    if config.base_url:
        kwargs["base_url"] = config.base_url

    client = openai.OpenAI(**kwargs)

    create_kwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
    }
    if tools:
        create_kwargs["tools"] = tools
    if tool_choice and tools:
        create_kwargs["tool_choice"] = tool_choice

    try:
        response = client.chat.completions.create(**create_kwargs)
    except Exception as e:
        raise RuntimeError(f"OpenAI 兼容调用失败 ({config.provider}/{config.model}): {e}") from e

    choice = response.choices[0]
    message = choice.message

    # 提取 tool_calls
    tool_calls_list = None
    if message.tool_calls:
        tool_calls_list = []
        for tc in message.tool_calls:
            tool_calls_list.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            })

    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
        cache_detail = getattr(response.usage, 'prompt_cache_hit_tokens', None)
        cache_miss = getattr(response.usage, 'prompt_cache_miss_tokens', None)
        if cache_detail is not None:
            usage["cache_hit_tokens"] = cache_detail
        if cache_miss is not None:
            usage["cache_miss_tokens"] = cache_miss
        _record_token_usage(usage, config.model, source)

    return {
        "content": message.content,
        "tool_calls": tool_calls_list,
        "usage": usage,
        "finish_reason": "tool_calls" if tool_calls_list else choice.finish_reason,
    }


def _convert_openai_tools_to_anthropic(openai_tools: list[dict]) -> list[dict]:
    """将 OpenAI function calling schema 转为 Anthropic 工具格式"""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in openai_tools
    ]


def _convert_messages_for_anthropic(messages: list[dict]) -> list[dict]:
    """将 OpenAI 格式的消息列表转为 Anthropic 格式

    关键差异：
    - Anthropic 没有 "tool" role，需要用 tool_result content block
    - assistant 的 tool_calls 需要转为 tool_use content block
    - 不支持 system role 混在 messages 中
    """
    converted = []
    for msg in messages:
        role = msg.get("role")

        if role == "system":
            # system 跳过，由 system 参数单独传
            continue

        elif role == "user":
            converted.append({"role": "user", "content": msg.get("content", "")})

        elif role == "assistant":
            content_blocks = []
            if msg.get("content"):
                content_blocks.append({"type": "text", "text": msg["content"]})
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    })
            if content_blocks:
                converted.append({"role": "assistant", "content": content_blocks})

        elif role == "tool":
            # tool result → 转为 user message with tool_result block
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }]
            })

    return converted


def _anthropic_nonstream(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
    source: str = 'chat',
) -> dict:
    """Anthropic 协议的非流式调用"""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK 未安装") from e

    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = anthropic.Anthropic(**kwargs)

    # 提取 system prompt
    system_text = ""
    for m in messages:
        if m.get("role") == "system":
            system_text = m.get("content", "")
            break

    # 转换消息格式
    converted_msgs = _convert_messages_for_anthropic(messages)

    create_kwargs = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "system": system_text,
        "messages": converted_msgs,
    }
    if tools:
        create_kwargs["tools"] = _convert_openai_tools_to_anthropic(tools)

    try:
        response = client.messages.create(**create_kwargs)
    except Exception as e:
        raise RuntimeError(f"Anthropic 调用失败 ({config.model}): {e}") from e

    # 解析响应
    content_text = ""
    tool_calls_list = []
    for block in response.content:
        if block.type == "text":
            content_text += block.text
        elif block.type == "tool_use":
            tool_calls_list.append({
                "id": block.id,
                "type": "function",
                "function": {
                    "name": block.name,
                    "arguments": json.dumps(block.input),
                }
            })

    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        _record_token_usage(usage, config.model, source)

    return {
        "content": content_text or None,
        "tool_calls": tool_calls_list or None,
        "usage": usage,
        "finish_reason": "tool_calls" if tool_calls_list else "stop",
    }


# ── 测试钩子（让单元测试可以 mock provider） ───────────────────
def _is_openai_compatible(provider: str) -> bool:
    return provider in _OPENAI_COMPATIBLE


def _record_token_usage(usage: dict, model: str = '', source: str = 'chat'):
    """将 usage 信息写入 token_usage 表（非阻塞，失败不影响主流程）

    由 stream 内部调用，每次 usage chunk 到达时触发。
    因为 stream_options={"include_usage": True} 只在流末尾发一次 usage，
    所以不会重复写入。
    """
    try:
        from core.database import StatsDB
        # 获取单例需要 db_path，通过 _instance 直接访问
        if StatsDB._instance is None:
            return
        StatsDB._instance.record_token_usage(
            prompt_tokens=usage.get('prompt_tokens', 0),
            completion_tokens=usage.get('completion_tokens', 0),
            cache_hit_tokens=usage.get('cache_hit_tokens', 0),
            cache_miss_tokens=usage.get('cache_miss_tokens', 0),
            model=model,
            source=source,
        )
        logger.info(
            f"[llm:usage] model={model} prompt={usage.get('prompt_tokens', 0)} "
            f"completion={usage.get('completion_tokens', 0)} "
            f"cache_hit={usage.get('cache_hit_tokens', 0)} "
            f"cache_miss={usage.get('cache_miss_tokens', 0)}"
        )
    except Exception as e:
        logger.warning(f"[llm:usage] record failed: {e}")
