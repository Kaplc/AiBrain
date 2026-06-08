"""
ChatLoop — 交互式聊天逻辑（无线程）
用户发送消息直接在此同步调用 LLM，无需经过后台线程。
prompt 构造通过 PromptPipeline 编排。
"""
from __future__ import annotations
import logging
import time
from typing import Iterator

from modules.LLM import LLMConfig, call_llm_stream
from .pipeline import PromptPipeline
from .pipeline.context import PromptContext

# 保留最近 N 轮对话（user + assistant）
MAX_HISTORY_TURNS = 10
_conversation_history: list[dict] = []  # [{"role": "user"/"assistant", "content": str}]

logger = logging.getLogger(__name__)


def _set_status(s: str):
    """线程安全设置当前状态"""
    try:
        from .chat_mod import ChatManager
        ChatManager.get_instance().set_status(s)
    except Exception:
        pass


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
) -> Iterator[dict]:
    """发送消息到 LLM，流式返回 token

    自动将消息写入工作记忆 input.json 并触发 package 搜索，
    通过 PromptPipeline 构造 system prompt。

    Args:
        prompt: 用户输入
        provider/model/api_key/base_url: LLM 配置

    Yields:
        {"type": "token", "content": str}
        {"type": "usage", ...}
        {"type": "done"}
        {"type": "error", "message": str}
    """
    try:
        logger.info(f"[loop] send_message start: prompt={prompt[:60]!r}")

        # 0. 写入工作记忆 + 触发 package 搜索
        _set_status("分析记忆")
        try:
            from modules.brain.memory.workmemory import get_work_memory
            wm = get_work_memory()
            wm.input_mem_write(prompt)
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
        )
        pipeline = PromptPipeline.get_instance()
        system_prompt = pipeline.run(ctx)
        memory_ref = ctx.metadata.get("_memory_reference", "")
        logger.info(f"[loop] system_prompt:\n{system_prompt}")
        if memory_ref:
            logger.info(f"[loop] memory_ref:\n{memory_ref[:200]}")

        # 3. 构建 messages 数组
        #    system:   人设/规则
        #    user:     记忆参考信息（独立消息，作为上下文参考）
        #    history:  历史 user/assistant 轮次
        #    user:     当前提问
        global _conversation_history
        msgs = [{"role": "system", "content": system_prompt}] if system_prompt else []
        if memory_ref:
            msgs.append({"role": "user", "content": f"参考信息：\n{memory_ref}"})
        for turn in _conversation_history[-MAX_HISTORY_TURNS * 2:]:
            msgs.append(turn)
        msgs.append({"role": "user", "content": prompt})

        # 4. 调用 LLM
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
        _set_status("生成回复")
        full_response: list[str] = []
        token_count = 0
        for chunk in call_llm_stream(config=cfg, messages=msgs):
            token = chunk.get('content', '')
            if token:
                full_response.append(token)
                token_count += 1
            yield {"type": "token", "content": token}
            if chunk.get('usage'):
                yield {
                    "type": "usage",
                    "prompt_tokens": chunk['usage'].get('prompt_tokens', 0),
                    "completion_tokens": chunk['usage'].get('completion_tokens', 0),
                }

        # 记录本轮对话到历史
        assistant_text = "".join(full_response)
        _conversation_history.append({"role": "user", "content": prompt})
        _conversation_history.append({"role": "assistant", "content": assistant_text})
        # 超出上限时删最旧的轮次
        while len(_conversation_history) > MAX_HISTORY_TURNS * 2:
            _conversation_history.pop(0)
            _conversation_history.pop(0)

        # 写入工作记忆 output.md（含用户提问 + LLM 回复）
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
