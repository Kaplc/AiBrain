"""
ContextCompressAgent — 对话上下文压缩 Agent

输入：旧对话条目列表 [{"role": "user/assistant", "content": str}, ...]
输出：压缩后的条目列表 [{"user": str, "assistant": str}, ...]
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from modules.LLM import LLMConfig, get_llm_manager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个对话压缩助手。分析多轮对话的内容变化，按主题分段，
每段压缩为一条 user+assistant，保留核心信息，删除冗余。

规则：
- 输出格式：[{"user": "...", "assistant": "..."}, ...]
- 按话题变化分段，每个独立话题输出一条
- 同一话题的多轮合并为一条
- 保留技术细节、决策、具体数值
- 删除客套话、重复表述、语气词
- 每条 user ≤ 200 字，assistant ≤ 300 字
- 只输出 JSON 数组，不要添加额外说明"""


class ContextCompressAgent(BaseAgent):
    name = "context_compress"
    description = "按主题分段压缩旧对话"
    system_prompt = SYSTEM_PROMPT
    enable_thinking = False

    def run(self, input_data: Any, **kwargs) -> list[dict]:
        """压缩旧对话条目

        Args:
            input_data: {"entries": [{"role": str, "content": str}, ...]}

        Returns:
            [{"user": str, "assistant": str}, ...]
        """
        if not isinstance(input_data, dict) or "entries" not in input_data:
            logger.warning("[agent:context_compress] invalid input_data")
            return []

        entries = input_data["entries"]
        if not entries:
            return []

        # 构建 user prompt：将消息对格式化为对话文本
        user_prompt = self._format_entries(entries)

        config = kwargs.get("config") or LLMConfig.from_settings()
        try:
            mgr = get_llm_manager()
            raw = mgr.complete(self.system_prompt, user_prompt, config)
        except Exception as e:
            logger.warning(f"[agent:context_compress] LLM call failed: {e}")
            return self._fallback(entries)

        result = self._parse(raw)
        if not result:
            logger.warning("[agent:context_compress] parse failed, using fallback")
            return self._fallback(entries)

        logger.info(f"[agent:context_compress] compressed {len(entries)} msgs -> {len(result)} entries")
        return result

    def _format_entries(self, entries: list[dict]) -> str:
        """将消息列表格式化为对话文本"""
        lines = [f"请分段压缩以下 {len(entries) // 2} 轮对话：\n"]
        idx = 1
        for i in range(0, len(entries) - 1, 2):
            user_msg = entries[i].get("content", "")
            asst_msg = entries[i + 1].get("content", "") if i + 1 < len(entries) else ""
            lines.append(f"{idx}. 用户：{user_msg}")
            lines.append(f"   助手：{asst_msg}")
            idx += 1
        return "\n".join(lines)

    def _parse(self, raw: str) -> list[dict]:
        """解析 LLM 返回的 JSON 数组"""
        # 尝试提取 JSON 数组
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
            if not isinstance(data, list):
                return []
            # 验证每条都有非空的 user 和 assistant
            result = []
            for item in data:
                if isinstance(item, dict) and "user" in item and "assistant" in item:
                    user = str(item["user"]).strip()
                    asst = str(item["assistant"]).strip()
                    if user or asst:  # 至少有一条非空
                        result.append({"user": user, "assistant": asst})
            return result if result else []
        except (json.JSONDecodeError, Exception):
            return []

    def _fallback(self, entries: list[dict]) -> list[dict]:
        """降级处理：保留原始条目不压缩（每对合并为一条）"""
        result = []
        for i in range(0, len(entries) - 1, 2):
            user_msg = entries[i].get("content", "")
            asst_msg = entries[i + 1].get("content", "") if i + 1 < len(entries) else ""
            result.append({"user": user_msg, "assistant": asst_msg})
        return result
