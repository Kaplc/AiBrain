"""LLM 记忆提炼（T005 主路径 / FR-002）

把 output.json 的完整对话记录（用户 + 猫猫）整体发给 LLM，由 LLM 统一识别并
提炼出值得长期保存的记忆。符合用户要求：
「把所有 output 消息全发过去 → 统一识别和提炼」。

设计：
  - 一次 LLM 调用处理整段对话记录，输出提炼出的记忆列表（0~N 条）。
  - LLM 失败/不可用 → 返回空列表，由 orchestrator 回退到规则评分。
  - 走新模块 modules.LLM（项目约定），配置复用设置→LLM。
  - JSON 解析容错复用既有模式（直解 → ```json 块 → 首个 {...}）。

输入对话已过 redaction（敏感片段已被屏蔽/过滤）。
"""
from __future__ import annotations

import json
import logging
import re

from .contracts import (
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
    clamp,
)

logger = logging.getLogger("memory.consolidation.judge")

_VALID_KINDS = {
    MEMORY_KIND_PREFERENCE, MEMORY_KIND_TASK, MEMORY_KIND_FACT,
    MEMORY_KIND_RELATION, MEMORY_KIND_DECISION, MEMORY_KIND_OTHER,
}

# 一次 LLM 调用最多处理的对话条目数（output.json FIFO 上限 100）
MAX_BATCH = 100

_SYSTEM_PROMPT = (
    "你是一个记忆提炼器。给你一段近期对话记录（用户和猫猫的交流），"
    "你的任务是从中识别并提炼出值得长期保存的记忆。\n"
    "\n"
    "值得提炼：\n"
    "1. 长期偏好（表达方式、工具偏好、工作节奏、习惯）\n"
    "2. 持续任务和承诺（待办、约定、下次要继续的事）\n"
    "3. 反复出现的环境事实（常用目录、项目约束、身份信息、操作习惯）\n"
    "4. 重要关系语境（用户对系统的期待、称呼、关系变化）\n"
    "5. 明显影响后续行动的决定或结论\n"
    "\n"
    "不要提炼：无意义闲聊、单次短暂情绪、低信息量重复表达、敏感私密信息、"
    "对当前单次任务的临时响应。\n"
    "\n"
    "把每条提炼的记忆**归一化为一句简洁的第三人称陈述句**（例如把「我喜欢用 VSCode」"
    "提炼为「用户偏好使用 VSCode 编辑器」）。一条对话可能提炼出 0 条或多条记忆。\n"
    "memory_kind 取值：preference / task / fact / relation / decision / other。\n"
    "source_seq 填这条记忆来源的对话序号。\n"
    "\n"
    "只输出一个 JSON 对象，格式：\n"
    '{"extracted": [{"source_seq": 181, "summary": "归一化陈述句", '
    '"memory_kind": "preference", "importance": 0.8, "reason": "稳定编辑器偏好"}]}'
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
    """LLM 记忆提炼器。"""

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
        base["temperature"] = 0.2          # 提炼要稳定
        base["max_tokens"] = 256000
        # 全量对话提炼，消息可能很长，超时 3 分钟
        base["timeout"] = get_brain_config().get("consolidation_timeout_seconds", 180)
        base["thinking_mode"] = False
        return LLMConfig.from_dict(base)

    def _format_transcript(self, transcript: list[dict]) -> str:
        """把对话记录格式化为 LLM 可读文本（完整内容，不截断）。"""
        lines = ["近期对话记录（[seq] 为序号）：\n"]
        for e in transcript:
            seq = e.get("seq", "")
            user = (e.get("user") or "").strip()
            assistant = (e.get("assistant") or "").strip()
            if user and assistant:
                lines.append(f"[{seq}] 用户：{user}")
                lines.append(f"      猫猫：{assistant}")
            elif user:
                lines.append(f"[{seq}] 用户：{user}")
            elif assistant:
                lines.append(f"[{seq}] 猫猫（主动）：{assistant}")
        lines.append(
            "\n请从上面这段对话中识别并提炼值得长期保存的记忆，"
            "归一化 summary，返回 JSON：{\"extracted\": [...]}"
        )
        return "\n".join(lines)

    def _call_with_retry(self, cfg, batch: list[dict], *, max_retries: int = 3) -> str:
        """带重试的 LLM 调用：最多 max_retries 次，间隔 2/4/6 秒递增。"""
        import time as _t
        from modules.LLM import get_llm_manager
        user_prompt = self._format_transcript(batch)
        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                raw = get_llm_manager().complete(_SYSTEM_PROMPT, user_prompt, cfg)
                if attempt > 1:
                    logger.info(f"[consolidation_judge] llm succeeded on attempt {attempt}")
                return raw
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    wait = 2 * attempt
                    logger.warning(
                        f"[consolidation_judge] llm attempt {attempt}/{max_retries} failed: {e}, "
                        f"retry in {wait}s"
                    )
                    _t.sleep(wait)
        raise last_err  # type: ignore[misc]

    def extract(
        self,
        transcript: list[dict],
        *,
        mock_response: str | None = None,
    ) -> dict:
        """从对话记录中统一提炼记忆。

        Args:
            transcript: [{"seq": int, "user": str, "assistant": str}, ...]

        Returns:
            {
                "ok": bool,
                "extracted": [{source_seq, summary, memory_kind, importance, reason}, ...],
                "error": str,
            }
            LLM 失败时 ok=False、extracted=[]，由调用方回退规则评分。
        """
        if not transcript:
            return {"ok": True, "extracted": [], "error": ""}

        batch = transcript[:MAX_BATCH]
        try:
            if mock_response is not None:
                raw = mock_response
            else:
                from modules.LLM import get_llm_manager
                cfg = self._build_llm_config()
                ok, err = cfg.validate()
                if not ok:
                    return {"ok": False, "extracted": [], "error": f"invalid llm config: {err}"}
                raw = self._call_with_retry(cfg, batch)
        except Exception as e:
            logger.warning(f"[consolidation_judge] llm call failed after retries: {e}")
            return {"ok": False, "extracted": [], "error": str(e)}

        parsed = _parse_json(raw)
        if not isinstance(parsed, dict):
            logger.warning(f"[consolidation_judge] parse failed: {raw[:120]}")
            return {"ok": False, "extracted": [], "error": "judge output not json"}

        valid_seqs = {int(e.get("seq", 0)) for e in batch if e.get("seq")}
        extracted: list[dict] = []
        for item in parsed.get("extracted", []) or []:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary", "") or "").strip()[:240]
            if not summary:
                continue
            try:
                seq = int(item.get("source_seq", 0) or 0)
            except (TypeError, ValueError):
                seq = 0
            kind = str(item.get("memory_kind", MEMORY_KIND_OTHER)) or MEMORY_KIND_OTHER
            if kind not in _VALID_KINDS:
                kind = MEMORY_KIND_OTHER
            extracted.append({
                "source_seq": seq,
                "summary": summary,
                "memory_kind": kind,
                "importance": clamp(float(item.get("importance", 0.6) or 0.6)),
                "reason": str(item.get("reason", "") or "").strip()[:160],
            })
        logger.info(f"[consolidation_judge] extracted {len(extracted)} memories from {len(batch)} entries")
        return {"ok": True, "extracted": extracted, "error": ""}


_judge: ConsolidationJudge | None = None


def get_consolidation_judge() -> ConsolidationJudge:
    global _judge
    if _judge is None:
        _judge = ConsolidationJudge()
    return _judge
