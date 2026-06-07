"""
MemorySearchAgent — 根据对话分析需要搜索什么

输入：当前用户消息 + 近期历史对话
输出：需要搜索的文本描述列表（可关键词、可事件、可描述）
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from modules.LLM import LLMConfig, get_llm_manager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个记忆检索分析助手。根据用户的当前提问，生成一条完整的搜索语句去记忆库中查找相关内容。

规则：
1. 只输出**一条**完整的自然语言语句，用于向量搜索
2. 精炼用户的当前提问，提取核心搜索意图
3. 用完整的句子描述，不要用关键词拼接
4. 去掉过于泛化的词，如果是简单问候如"你好""hello"可直接使用原文

输出格式（严格遵守JSON）：
{"query": "完整的搜索语句"}"""


class MemorySearchAgent(BaseAgent):
    name = "memory_search"
    description = "分析需要搜索什么"
    system_prompt = SYSTEM_PROMPT
    enable_thinking = False

    def run(self, input_data: Any, **kwargs) -> dict:
        current = input_data.get("current", "") if isinstance(input_data, dict) else str(input_data)
        user_prompt = f"【当前消息】\n{current}"

        config = kwargs.get("config") or LLMConfig.from_settings()
        if self.enable_thinking and config.provider == "deepseek":
            config = LLMConfig(
                provider=config.provider, model=config.model,
                api_key=config.api_key, base_url=config.base_url,
                thinking_mode=True,
            )
        try:
            mgr = get_llm_manager()
            raw = mgr.complete(self.system_prompt, user_prompt, config)
        except Exception as e:
            logger.warning(f"[agent:memory_search] LLM call failed: {e}")
            return {"queries": [current[:80]]}

        result = self._parse(raw)
        logger.info(f"[agent:memory_search] query={result.get('query')!r}")
        return result

    def _parse(self, raw: str) -> dict:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                q = data.get("query", "")
                return {"query": str(q).strip() if q else ""}
            except Exception:
                pass
        return {"query": ""}


def _make_step():
    return MemorySearchAgent()
