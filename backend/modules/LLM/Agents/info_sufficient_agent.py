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

SYSTEM_PROMPT = """你是一个信息判断助手。给定用户的问题和搜索到的记忆，判断这些记忆是否足够回答用户的问题。

规则：
1. 如果记忆中包含回答该问题所需的关键信息 → enough=true
2. 如果记忆不相关或信息不足 → enough=false
3. 如果只是简单问候（你好、你是谁等），记忆中有基本介绍即可

输出格式（严格遵守JSON）：
{"enough": true/false, "reason": "判断理由"}"""


class InfoSufficientAgent(BaseAgent):
    name = "info_sufficient"
    description = "判断记忆是否足够回答问题"
    system_prompt = SYSTEM_PROMPT
    enable_thinking = False

    def run(self, input_data: Any, **kwargs) -> dict:
        """判断记忆是否足够回答

        Args:
            input_data: {"query": str, "memories": [{"id": str, "text": str}, ...]}

        Returns:
            {"enough": bool, "reason": str}
        """
        query = input_data.get("query", "") if isinstance(input_data, dict) else ""
        memories = input_data.get("memories", []) if isinstance(input_data, dict) else []

        if not query:
            return {"enough": False, "reason": "query为空"}

        # 记忆为空 → 不足
        if not memories:
            return {"enough": False, "reason": "没有搜索到相关记忆"}

        # 构建候选列表
        lines = [f"用户问题：{query}", "", "搜索到的记忆："]
        for i, m in enumerate(memories[:8]):
            text = m.get("text", "") or m.get("memory", "")
            lines.append(f"{i+1}. {text[:150]}")
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
