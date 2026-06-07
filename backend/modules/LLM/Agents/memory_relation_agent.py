"""
MemoryRelationAgent — 判断记忆与查询的相关性
输入：query + 候选记忆列表
输出：按相关度排序的关联记忆 ID 列表
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from modules.LLM import LLMConfig, get_llm_manager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个记忆相关性判断助手。给定一个搜索查询和一组候选记忆，选出相关的记忆。

规则：
1. 相关 = 记忆内容和查询的主题/人物/事件有直接联系
2. 按相关度从高到低排序
3. 最多返回10条，不足10条就只返回有的
4. 宁可漏掉也不要误判不相关的记忆

输出格式（严格遵守JSON，不要其他内容）：
{"related": [3, 0, 7, 2, 5]}"""


class MemoryRelationAgent(BaseAgent):
    name = "memory_relation"
    description = "判断记忆与查询的相关性"
    system_prompt = SYSTEM_PROMPT
    enable_thinking = False

    def run(self, input_data: Any, **kwargs) -> list[str]:
        """判断候选记忆与查询的相关性

        Args:
            input_data: {"query": str, "candidates": [{"id": str, "text": str}, ...]}

        Returns:
            相关记忆的 ID 列表（按相关度排序）
        """
        query = input_data.get("query", "") if isinstance(input_data, dict) else ""
        candidates = input_data.get("candidates", []) if isinstance(input_data, dict) else []

        if not query or not candidates:
            return []

        # 构建候选列表文本
        lines = []
        for i, c in enumerate(candidates):
            text = c.get("text", "") or c.get("memory", "")
            lines.append(f"{i}. {text[:120]}")
        user_prompt = f"Query: {query}\n\n候选记忆:\n" + "\n".join(lines)

        # 调 LLM
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
            logger.warning(f"[agent:memory_relation] LLM call failed: {e}")
            return [c["id"] for c in candidates[:5]]

        # 解析
        indices = self._parse(raw, len(candidates))
        related_ids = [candidates[i]["id"] for i in indices if i < len(candidates)]
        logger.info(f"[agent:memory_relation] query={query[:40]!r} candidates={len(candidates)} related={len(related_ids)}")
        return related_ids

    def _parse(self, raw: str, candidate_count: int) -> list[int]:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                indices = data.get("related", [])
                if isinstance(indices, list):
                    return [i for i in indices if isinstance(i, int) and 0 <= i < candidate_count]
            except Exception:
                pass
        # fallback
        numbers = re.findall(r'\b(\d+)\b', raw)
        return [int(n) for n in numbers if int(n) < candidate_count]


def _make_step():
    return MemoryRelationAgent()
