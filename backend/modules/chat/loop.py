"""
ChatLoop — 交互式聊天逻辑（无线程）
用户发送消息直接在此同步调用 LLM，无需经过后台线程。
prompt 构造通过 PromptPipeline 编排。

tools_enabled=True 时进入 Tool Loop（非流式调用 + 工具执行循环），
tools_enabled=False 时走原有流式路径（行为完全不变）。
"""
from __future__ import annotations
import json
import logging
import time
from typing import Iterator

from modules.LLM import LLMConfig, get_llm_manager
from .pipeline import PromptPipeline
from .pipeline.context import PromptContext

# 保留最近 N 轮对话（一个轮次 = user msg + 后续所有非 user msg）
MAX_HISTORY_TURNS = 10
MAX_TOOL_ROUNDS = 999
_conversation_history: list[dict] = []

logger = logging.getLogger(__name__)


def _set_status(s: str):
    """线程安全设置当前状态"""
    try:
        from .chat_mod import ChatManager
        ChatManager.get_instance().set_status(s)
    except Exception:
        pass


def _trim_history():
    """按 user message 边界裁剪 _conversation_history，保留最近 MAX_HISTORY_TURNS 个轮次"""
    global _conversation_history
    # 找到所有 user message 的位置
    turn_starts = []
    for i, msg in enumerate(_conversation_history):
        if msg.get("role") == "user":
            turn_starts.append(i)

    if len(turn_starts) <= MAX_HISTORY_TURNS:
        return

    # 保留最后 MAX_HISTORY_TURNS 个轮次
    cutoff = turn_starts[-MAX_HISTORY_TURNS]
    _conversation_history = _conversation_history[cutoff:]


def send_message(
    prompt: str,
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = 120,
    tools_enabled: bool = False,
    system_persona: str = "",
) -> Iterator[dict]:
    """发送消息到 LLM，流式返回 token 或 Tool Loop 结果

    tools_enabled=True 时走 Tool Loop（非流式调用 + 工具执行循环），
    tools_enabled=False 时走原有流式路径（行为完全不变）。

    Yields:
        {"type": "tool_history", "tools": [...]}  (仅 tools_enabled)
        {"type": "token", "content": str}
        {"type": "usage", ...}
        {"type": "done"}
        {"type": "error", "message": str}
    """
    try:
        logger.info(f"[loop] send_message start: prompt={prompt[:60]!r} tools={tools_enabled}")

        # 0. 压缩后重载检查
        try:
            from .compression.context_compress import reload_if_needed
            reload_if_needed(_conversation_history)
        except Exception as e:
            logger.warning(f"[loop] compress reload failed: {e}")

        # 0.1 写入工作记忆 + (非工具模式时) 触发 package 搜索
        _set_status("分析记忆")
        try:
            from modules.brain.memory.workmemory import get_work_memory
            wm = get_work_memory()
            wm.input_mem_write(prompt)
            if not tools_enabled:
                wm.handle_packagemem()
            logger.info("[loop] workmemory updated")
        except Exception as e:
            logger.warning(f"[loop] workmemory update failed: {e}")

        # 1. 获取工作记忆
        work_memory = {}
        try:
            from modules.brain.memory.workmemory import get_work_memory
            work_memory = get_work_memory().get_workmem()
        except Exception as e:
            logger.warning(f"[loop] get workmemory failed: {e}")

        # 2. 通过 PromptPipeline 构造 system prompt + 记忆参考
        ctx = PromptContext(
            user_message=prompt,
            work_memory=work_memory,
            system_persona=system_persona,
        )
        pipeline = PromptPipeline.get_instance()
        system_prompt = pipeline.run(ctx)
        memory_ref = ctx.metadata.get("_memory_reference", "")
        logger.info(f"[loop] system_prompt:\n{system_prompt}")
        if memory_ref:
            logger.info(f"[loop] memory_ref:\n{memory_ref[:200]}")

        # 3. 构建 messages 数组
        #    注意：memory_ref 放在历史对话之后，这样 [system] + [历史] 前缀
        #    在多轮对话间保持稳定，提高 DeepSeek KV 缓存命中率
        global _conversation_history
        msgs = [{"role": "system", "content": system_prompt}] if system_prompt else []
        for turn in _conversation_history:
            msgs.append(turn)
        if memory_ref:
            msgs.append({"role": "user", "content": f"参考信息：\n{memory_ref}"})
        msgs.append({"role": "user", "content": prompt})

        # 4. LLM 配置
        cfg = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        logger.info(f"[loop] calling LLM: {len(msgs)} msgs, provider={provider} model={model}")
        logger.info(f"[loop]  └─ system: {system_prompt[:300]}")
        logger.info(f"[loop]  └─ user: {prompt[:200]}")

        # ════════════════════════════════════════════════════════
        # Tool Loop 路径（tools_enabled=True 且注册表非空）
        # ════════════════════════════════════════════════════════
        if tools_enabled:
            try:
                from modules.LLM.tools.registry import get_tool_registry
                reg = get_tool_registry()
                tool_schemas = reg.get_openai_schemas()
            except Exception as e:
                logger.warning(f"[loop] tool registry failed, falling back to stream: {e}")
                tool_schemas = []

        if tools_enabled and tool_schemas:
            yield from _tool_loop(cfg, msgs, prompt, tool_schemas)
            return

        # ════════════════════════════════════════════════════════
        # 流式路径（tools_enabled=False 或无工具注册）
        # ════════════════════════════════════════════════════════
        _set_status("生成回复")
        full_response: list[str] = []
        token_count = 0
        last_prompt_tokens = 0
        for chunk in get_llm_manager().stream_messages(msgs, cfg):
            token = chunk.get('content', '')
            if token:
                full_response.append(token)
                token_count += 1
            yield {"type": "token", "content": token}
            if chunk.get('usage'):
                last_prompt_tokens = chunk['usage'].get('prompt_tokens', 0)
                yield {
                    "type": "usage",
                    "prompt_tokens": last_prompt_tokens,
                    "completion_tokens": chunk['usage'].get('completion_tokens', 0),
                }

        # 记录本轮对话到历史
        assistant_text = "".join(full_response)
        _conversation_history.append({"role": "user", "content": prompt})
        _conversation_history.append({"role": "assistant", "content": assistant_text})

        # 后台压缩检查（基于 Token 占比）
        try:
            from .compression.context_compress import try_spawn_compress
            try_spawn_compress(_conversation_history, last_prompt_tokens)
        except Exception as e:
            logger.warning(f"[loop] compress spawn failed: {e}")

        # 写入工作记忆 output.md
        try:
            from modules.brain.memory.workmemory import get_work_memory
            get_work_memory().output_mem_write(assistant_text, user_prompt=prompt)
            logger.info("[loop] assistant reply written to workmemory output.md")
        except Exception as e:
            logger.warning(f"[loop] output_mem_write failed: {e}")

        logger.info(f"[loop] LLM done: tokens={token_count} total_chars={len(assistant_text)}")
        yield {"type": "done"}

    except Exception as e:
        logger.exception(f"[loop] send_message failed: {e}")
        yield {"type": "error", "message": str(e)}


def _tool_loop(
    cfg: LLMConfig,
    msgs: list[dict],
    prompt: str,
    tool_schemas: list[dict],
) -> Iterator[dict]:
    """Tool Loop — 非流式 LLM 调用 + 工具执行循环

    流程：
    1. 非流式调 LLM（带 tools schemas）
    2. finish_reason == "tool_calls" → 执行工具 → 追加结果 → 循环
    3. finish_reason == "stop" → 取 content 作为最终回复
    4. 超 8 轮 → 兜底消息
    5. yield tool_history → yield final text tokens → yield done
    """
    from modules.LLM.tools.registry import get_tool_registry
    reg = get_tool_registry()

    tool_history = []
    final_text = ""
    total_prompt_tokens = 0

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        _set_status(f"工具调用 (第{round_num}轮)")
        logger.info(f"[loop] tool loop round {round_num}")

        try:
            response = get_llm_manager().complete_with_tools(
                messages=msgs,
                config=cfg,
                tools=tool_schemas,
                tool_choice="auto",
            )
        except Exception as e:
            logger.error(f"[loop] tool loop LLM call failed: {e}")
            final_text = f"抱歉，AI 调用时出错：{e}"
            break

        # 转发 usage（累计总 prompt_tokens）
        if response.get("usage"):
            round_tokens = response["usage"].get("prompt_tokens", 0)
            total_prompt_tokens += round_tokens
            yield {
                "type": "usage",
                "prompt_tokens": round_tokens,
                "completion_tokens": response["usage"].get('completion_tokens', 0),
            }

        finish = response.get("finish_reason")

        if finish == "tool_calls" and response.get("tool_calls"):
            # 追加 assistant message（含 tool_calls）
            assistant_msg = {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": response["tool_calls"],
            }
            msgs.append(assistant_msg)

            # 执行每个 tool call
            for tc in response["tool_calls"]:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}
                tool_call_id = tc["id"]

                logger.info(f"[loop] executing tool: {fn_name} args={fn_args}")
                # 实时推送工具调用事件到前端
                yield {
                    "type": "tool_call",
                    "name": fn_name,
                    "arguments": fn_args,
                }
                result_str = reg.execute(fn_name, fn_args)
                logger.info(f"[loop] tool result: {result_str[:200]}")

                tool_history.append({
                    "name": fn_name,
                    "arguments": fn_args,
                    "result": result_str[:500],
                })

                # 追加 tool result message
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })

            # 继续下一轮
            continue

        else:
            # LLM 返回文本 → 结束循环
            final_text = response.get("content") or "抱歉，我无法完成请求。"
            break
    else:
        # 超限终止（理论上不会触发）
        final_text = "（工具调用次数过多，已终止）"
        logger.warning("[loop] tool loop exceeded max rounds")

    # ── Tool Loop 结束后 ──

    # 1. yield tool_history
    if tool_history:
        yield {"type": "tool_history", "tools": tool_history}

    # 2. yield final text
    _set_status("生成回复")
    yield {"type": "token", "content": final_text}

    # 3. 保存对话到 _conversation_history（只存 user + assistant 文本，不存 tool 消息）
    _conversation_history.append({"role": "user", "content": prompt})
    _conversation_history.append({"role": "assistant", "content": final_text})

    # 后台压缩检查（基于 Token 占比，使用累计 prompt_tokens）
    try:
        from .compression.context_compress import try_spawn_compress
        try_spawn_compress(_conversation_history, total_prompt_tokens)
    except Exception as e:
        logger.warning(f"[loop] compress spawn failed: {e}")

    # 4. 写入工作记忆
    try:
        from modules.brain.memory.workmemory import get_work_memory
        get_work_memory().output_mem_write(final_text, user_prompt=prompt)
        logger.info("[loop] tool loop output written to workmemory")
    except Exception as e:
        logger.warning(f"[loop] output_mem_write failed: {e}")

    logger.info(f"[loop] tool loop done: {len(tool_history)} tool calls, chars={len(final_text)}")
    yield {"type": "done"}
