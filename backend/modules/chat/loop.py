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
_tool_memory: list[dict] = []  # 最近一轮 Tool Loop 的工具消息，不落盘

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
    global _conversation_history
    try:
        logger.info(f"[loop] send_message start: prompt={prompt[:60]!r} tools={tools_enabled}")

        # 0. 加载/重载对话历史到内存
        try:
            from .compression.context_compress import reload_if_needed
            if not _conversation_history:
                # 首次对话：从 output.json 加载历史
                from modules.brain.memory.workmemory import get_work_memory
                entries = get_work_memory().output_mem_read()
                if entries:
                    for e in entries:
                        if e.get("user"):
                            _conversation_history.append({"role": "user", "content": e["user"]})
                        if e.get("assistant"):
                            _conversation_history.append({"role": "assistant", "content": e["assistant"]})
                    logger.info(f"[loop] loaded {len(entries)} entries from output.json → {len(_conversation_history)} msgs")
            else:
                reload_if_needed(_conversation_history)
        except Exception as e:
            logger.warning(f"[loop] history load failed: {e}")

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
        msgs = [{"role": "system", "content": system_prompt}] if system_prompt else []
        for turn in _conversation_history:
            msgs.append(turn)
        if _tool_memory:
            msgs.extend(_tool_memory)
            logger.info(f"[loop] injected tool memory: {len(_tool_memory)} msgs")
        if memory_ref:
            # 记忆检索视为工具调用，与 Hermes/OpenAI 规范一致
            msgs.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "mem_ctx", "type": "function", "function": {"name": "memory_search", "arguments": "{}"}}],
            })
            msgs.append({"role": "tool", "name": "memory_search", "tool_call_id": "mem_ctx", "content": memory_ref})
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
            # 统计 msgs 组成
            n_sys = 1 if msgs and msgs[0].get("role") == "system" else 0
            n_hist = sum(1 for m in msgs if m.get("role") in ("user", "assistant") and not m.get("tool_calls"))
            n_tool = sum(1 for m in msgs if m.get("role") == "tool" or m.get("tool_calls"))
            n_ref = sum(1 for m in msgs if m.get("tool_call_id") == "mem_ctx")
            logger.info(f"[loop] msgs composition: sys={n_sys} history={n_hist} tool_mem={n_tool} ref={n_ref} total={len(msgs)}")
            pre_tool_len = len(msgs)
            yield from _tool_loop(cfg, msgs, prompt, tool_schemas, pre_tool_len)
            return

        # ════════════════════════════════════════════════════════
        # 流式路径（tools_enabled=False 或无工具注册）
        # ════════════════════════════════════════════════════════
        if _tool_memory:
            logger.info(f"[loop] stream path with {len(_tool_memory)} tool memory msgs injected")
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
                logger.info(f"[loop] actual prompt_tokens from LLM: {last_prompt_tokens}")
                yield {
                    "type": "token_estimate",
                    "prompt_tokens": last_prompt_tokens,
                }
                yield {
                    "type": "usage",
                    "prompt_tokens": last_prompt_tokens,
                    "completion_tokens": chunk['usage'].get('completion_tokens', 0),
                }

        # 记录本轮对话到历史
        assistant_text = "".join(full_response)
        logger.info(f"[loop] LLM final response ({len(assistant_text)} chars): {assistant_text[:200]}{'...' if len(assistant_text) > 200 else ''}")
        _conversation_history.append({"role": "user", "content": prompt})
        _conversation_history.append({"role": "assistant", "content": assistant_text})

        # 后台压缩检查 + token 用量记录
        try:
            from .compression.context_compress import try_spawn_compress
            try_spawn_compress(_conversation_history, last_prompt_tokens)
            from .chat_mod import ChatManager
            ChatManager.get_instance().set_token_usage(last_prompt_tokens, token_count)
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
    pre_tool_len: int = 0,
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
    last_prompt_tokens = 0

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        _set_status(f"工具调用 (第{round_num}轮)")
        logger.info(f"[loop] tool loop round {round_num}")

        try:
            # 调用前 sanitize：移除孤儿 tool_call/tool_result 对
            from .compilation.sanitizer import sanitize_tool_pairs
            msgs = sanitize_tool_pairs(msgs)

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

        # 转发 LLM 返回的实际 token 数（取最后一轮，不累加）
        if response.get("usage"):
            round_tokens = response["usage"].get("prompt_tokens", 0)
            last_prompt_tokens = round_tokens
            last_completion_tokens = response["usage"].get('completion_tokens', 0)
            logger.info(f"[loop] actual prompt_tokens from LLM (round {round_num}): {round_tokens}")
            yield {
                "type": "token_estimate",
                "prompt_tokens": round_tokens,
            }
            yield {
                "type": "usage",
                "prompt_tokens": round_tokens,
                "completion_tokens": last_completion_tokens,
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

                logger.info(f"[loop] executing tool: {fn_name}")
                # 实时推送工具调用事件到前端
                yield {
                    "type": "tool_call",
                    "name": fn_name,
                    "arguments": fn_args,
                }
                result_str = reg.execute(fn_name, fn_args)

                tool_history.append({
                    "name": fn_name,
                    "arguments": fn_args,
                    "result": result_str[:500],
                })

                # 追加 tool result message（Hermes 风格：name=函数名）
                msgs.append({
                    "role": "tool",
                    "name": fn_name,
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

    # 0. 提取本轮 Tool Loop 的工具消息 → _tool_memory
    #    只有本轮确实调了工具才更新，没调则保留上一轮的记忆
    global _tool_memory
    _new_tool_msgs = [
        msg for msg in msgs[pre_tool_len:]
        if (msg["role"] in ("assistant", "tool") and msg["role"] != "assistant")
        or msg.get("tool_calls")
    ]
    if _new_tool_msgs:
        _tool_memory = _new_tool_msgs
        tool_roles = sorted(set(m.get("role", "?") for m in _tool_memory))
        logger.info(f"[loop] tool memory updated: {len(_tool_memory)} msgs [{', '.join(tool_roles)}]")
    else:
        logger.info(f"[loop] tool memory unchanged ({len(_tool_memory)} msgs, no tool calls this round)")

    # 1. yield tool_history
    if tool_history:
        yield {"type": "tool_history", "tools": tool_history}

    # 2. yield final text
    _set_status("生成回复")
    yield {"type": "token", "content": final_text}

    logger.info(f"[loop] LLM final response ({len(final_text)} chars): {final_text[:200]}{'...' if len(final_text) > 200 else ''}")

    # 3. 保存对话到 _conversation_history（只存 user + assistant 文本，不存 tool 消息）
    _conversation_history.append({"role": "user", "content": prompt})
    _conversation_history.append({"role": "assistant", "content": final_text})

    # 后台压缩检查 + token 用量记录（取最后一轮）
    logger.info(f"[loop] compress: check with last_prompt_tokens={last_prompt_tokens}")
    try:
        from .compression.context_compress import try_spawn_compress
        try_spawn_compress(_conversation_history, last_prompt_tokens)
        from .chat_mod import ChatManager
        ChatManager.get_instance().set_token_usage(last_prompt_tokens, last_completion_tokens)
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
