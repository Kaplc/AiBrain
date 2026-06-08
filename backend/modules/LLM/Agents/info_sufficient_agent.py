"""
InfoSufficientAgent — 判断搜索到的记忆是否足够回答用户问题
输入：query + 候选记忆列表
输出：是否足够回答
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from modules.LLM import LLMConfig, get_llm_manager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个信息判断助手。判断是否需要搜索长期记忆来回答用户的问题。

你可以获得两部分信息：
- 当前对话上下文（最近几轮对话）
- 搜索到的记忆（如果有）

规则：
1. 如果【对话上下文】本身已经**明确包含**回答所需的关键信息 → enough=true
2. 如果【当前对话上下文】不足以回答，但搜索到的【记忆】足够 → enough=true
3. 如果不足以回答 → enough=false
4. 如果当前问题是紧跟上一轮的追问、且上一轮对话已明确包含答案 → enough=true

重要：不要因为"AI可以根据自身身份回答"就跳过搜索。AI的自身身份来源于记忆，
对于"你是谁""你记得什么"等需要了解自身背景的问题，即使上下文看似足够也需要搜索记忆。
只有当前对话中已明确提及并包含了答案内容时，才判断为足够。

输出格式（严格遵守JSON）：
{"enough": true/false, "reason": "判断理由"}"""


class InfoSufficientAgent(BaseAgent):
    name = "info_sufficient"
    description = "判断记忆是否足够回答问题"
    system_prompt = SYSTEM_PROMPT
    enable_thinking = False

    def run(self, input_data: Any, **kwargs) -> dict:
        """判断是否足够回答（考虑对话上下文 + 搜索结果）

        Args:
            input_data:
                query: 当前用户问题
                memories: 搜索到的记忆（可选，无搜索时可省略）
                conversation: 最近对话上下文列表 [{role, content}, ...]（可选）

        Returns:
            {"enough": bool, "reason": str}
        """
        query = input_data.get("query", "") if isinstance(input_data, dict) else ""
        memories = input_data.get("memories", []) if isinstance(input_data, dict) else []
        conversation = input_data.get("conversation", []) if isinstance(input_data, dict) else []

        if not query:
            return {"enough": False, "reason": "query为空"}

        # 构建提示
        lines = [f"用户问题：{query}"]
        if conversation:
            lines.append("")
            lines.append("最近对话：")
            for turn in conversation[-4:]:  # 最近 2 轮
                role = turn.get("role", "user")
                content = turn.get("content", "")[:200]
                lines.append(f"{role}：{content}")
        if memories:
            lines.append("")
            lines.append("搜索到的记忆：")
            for i, m in enumerate(memories[:8]):
                text = m.get("text", "") or m.get("memory", "")
                lines.append(f"{i+1}. {text[:150]}")
        else:
            lines.append("")
            lines.append("（没有搜索到记忆）")
        user_prompt = "\n".join(lines)

        config = kwargs.get("config") or LLMConfig.from_settings()
        try:
            mgr = get_llm_manager()
            raw = mgr.complete(self.system_prompt, user_prompt, config)
        except Exception as e:
            logger.warning(f"[agent:info_sufficient] LLM call failed: {e}")
            return {"enough": True, "reason": "LLM不可用，默认继续"}

        result = self._parse(raw)
        logger.info(
            f"[agent:info_sufficient] enough={result.get('enough')} "
            f"reason={result.get('reason','')[:60]}"
        )
        return result

    def _parse(self, raw: str) -> dict:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                return {
                    "enough": bool(data.get("enough", True)),
                    "reason": str(data.get("reason", "")),
                }
            except Exception:
                pass
        return {"enough": True, "reason": "解析失败，默认继续"}


def _make_step():
    return InfoSufficientAgent()
