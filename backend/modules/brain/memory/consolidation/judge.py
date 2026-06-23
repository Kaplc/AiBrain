"""LLM 批量价值判断（T005 主路径 / FR-002）

收集近期 output 聊天后，**一次性批量**喂给 LLM，由 LLM 判断每条是否值得沉淀为
长期记忆，并产出归一化摘要、记忆类型、重要性、理由。符合用户要求：
「收集当前 output 所有聊天 → 分批给 LLM 判断 → 保存」。

设计：
  - 一次 LLM 调用处理整批候选（简单、省调用），输出严格 JSON。
  - LLM 失败/不可用 → 返回空决策列表，由 orchestrator 回退到规则评分（policy.py）。
  - 走新模块 modules.LLM（项目约定），配置复用设置→LLM（llm.json）。
  - JSON 解析容错复用既有模式（直解 → ```json 块 → 首个 {...}）。

输入候选已过 redaction（敏感片段已被屏蔽/过滤），不会把明文密码喂给 LLM。
"""
from __future__ import annotations

import json
import logging
import re

from .contracts import (
    MemoryCandidate,
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
    clamp,
)

logger = logging.getLogger("memory.consolidation.judge")

_VALID_KINDS = {
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
}

# 一次 LLM 调用最多判断的候选数（控制 prompt 长度 / 成本）
MAX_BATCH = 20

_SYSTEM_PROMPT = (
    "你是一个记忆沉淀判断器。给你一批近期对话输出，判断哪些值得沉淀为用户的长期记忆。\n"
    "\n"
    "值得保存：\n"
    "1. 长期偏好（表达方式、工具偏好、工作节奏、习惯）\n"
    "2. 持续任务和承诺（待办、约定、下次要继续的事）\n"
    "3. 反复出现的环境事实（常用目录、项目约束、身份信息、操作习惯）\n"
    "4. 重要关系语境（用户对系统的期待、称呼、关系变化）\n"
    "5. 明显影响后续行动的决定或结论\n"
    "\n"
    "不要保存：无意义闲聊、单次短暂情绪、低信息量重复表达、敏感私密信息。\n"
    "\n"
    "对输入的每一条输出，输出一个判断对象。把原始口语化的内容**归一化为一句简洁的"
    "第三人称陈述句**作为 summary（例如把「我喜欢用 VSCode」存为「用户偏好使用 VSCode 编辑器」）。\n"
    "memory_kind 取值：preference / task / fact / relation / decision / other。\n"
    "\n"
    "只输出一个 JSON 对象，格式：\n"
    '{"results": [{"index": 0, "save": true, "summary": "归一化陈述句", '
    '"memory_kind": "preference", "importance": 0.8, "reason": "稳定偏好"}]}'
)


def _parse_json(raw: str) -> dict | None:
    """容错解析 JSON（直解 → ```json 块 → 首个 {...}）。"""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


class ConsolidationJudge:
    """LLM 批量判断器。"""

    def _build_llm_config(self):
        from modules.LLM import LLMConfig
        from core.settings import ConfigManager
        from main_brain.config import get_brain_config
        llm_cfg = ConfigManager.get_instance().read_llm()
        base = {
            "provider": llm_cfg.get("provider", "openai"),
            "model": llm_cfg.get("model", "gpt-4o-mini"),
            "api_key": llm_cfg.get("api_key", ""),
            "base_url": llm_cfg.get("base_url", ""),
        }
        base["temperature"] = 0.2          # 判断要稳定
        base["max_tokens"] = 256000
        base["timeout"] = get_brain_config().get("judge_timeout_seconds", 20)
        base["thinking_mode"] = False
        return LLMConfig.from_dict(base)

    def _user_prompt(self, candidates: list[MemoryCandidate]) -> str:
        lines = ["近期输出列表（index 为序号）：\n"]
        for i, c in enumerate(candidates):
            tag = "用户" if c.source_type == "output" else "系统"
            lines.append(f"[{i}] ({tag} seq={c.source_seq}) {c.summary}")
        lines.append(
            "\n请对上面每一条输出一个判断，归一化 summary，返回 JSON："
            '{"results": [...]}'
        )
        return "\n".join(lines)

    def judge(
        self,
        candidates: list[MemoryCandidate],
        *,
        mock_response: str | None = None,
    ) -> dict:
        """批量判断。

        Returns:
            {
                "ok": bool,
                "decisions": {index(int): {save, summary, memory_kind, importance, reason}},
                "error": str,
            }
            LLM 失败时 ok=False、decisions={}，由调用方回退规则评分。
        """
        if not candidates:
            return {"ok": True, "decisions": {}, "error": ""}

        batch = candidates[:MAX_BATCH]
        try:
            if mock_response is not None:
                raw = mock_response
            else:
                from modules.LLM import get_llm_manager
                cfg = self._build_llm_config()
                ok, err = cfg.validate()
                if not ok:
                    return {"ok": False, "decisions": {}, "error": f"invalid llm config: {err}"}
                raw = get_llm_manager().complete(self._system_prompt(), self._user_prompt(batch), cfg)
        except Exception as e:
            logger.warning(f"[consolidation_judge] llm call failed: {e}")
            return {"ok": False, "decisions": {}, "error": str(e)}

        parsed = _parse_json(raw)
        if not isinstance(parsed, dict):
            logger.warning(f"[consolidation_judge] parse failed: {raw[:120]}")
            return {"ok": False, "decisions": {}, "error": "judge output not json"}

        decisions: dict[int, dict] = {}
        for item in parsed.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index", -1))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(batch):
                continue
            kind = str(item.get("memory_kind", MEMORY_KIND_OTHER)) or MEMORY_KIND_OTHER
            if kind not in _VALID_KINDS:
                kind = MEMORY_KIND_OTHER
            decisions[idx] = {
                "save": bool(item.get("save", False)),
                "summary": str(item.get("summary", "") or "").strip()[:240],
                "memory_kind": kind,
                "importance": clamp(float(item.get("importance", 0.5) or 0.5)),
                "reason": str(item.get("reason", "") or "").strip()[:160],
            }
        return {"ok": True, "decisions": decisions, "error": ""}


_judge: ConsolidationJudge | None = None


def get_consolidation_judge() -> ConsolidationJudge:
    global _judge
    if _judge is None:
        _judge = ConsolidationJudge()
    return _judge
