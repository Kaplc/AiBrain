"""BrainJudge — LLM 结构化决策（T003）

每轮循环由 LLM 输出一个 BrainJudgeDecision（JSON），代码执行副作用。judge 本身
不产生副作用、不调记忆/工具/状态——那是 adapter 的事。

LLM 走新模块 modules.LLM（项目约定：新功能关于 LLM 请求的都用 modules/LLM）。
配置复用 ~/.aibrain/config/mem0.json，按 judge_temperature / judge_timeout 覆盖。

JSON 解析容错复用项目既有模式（先 json.loads，再 ```json 代码块，再首个 {...}）。
schema 校验只做关键字段（next_action 枚举 / confidence 区间），非法则返回 abort。
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable

from .config import get_brain_config
from .contracts import (
    ACTIONS, REACTIVE, BACKGROUND, BrainJudgeDecision,
)

logger = logging.getLogger("main_brain.judge")

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[judge] load prompt {name} failed: {e}")
        return ""


_REACTIVE_PROMPT = _load_prompt("brain_judge_reactive.md")
_IDLE_PROMPT = _load_prompt("brain_judge_idle.md")


def _persona() -> dict:
    """轻量人格（name / traits），注入 prompt。失败回退默认。"""
    try:
        from modules.brain.state import get_self_model
        sm = get_self_model().get()
        return {
            "name": sm.get("name", "猫猫"),
            "traits": "、".join(sm.get("traits", []) or ["好奇", "随性"]),
        }
    except Exception:
        return {"name": "猫猫", "traits": "好奇、随性"}


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
    logger.warning(f"[judge] JSON parse failed: {raw[:120]}")
    return None


@dataclass
class JudgeResult:
    """judge 单次调用结果（含诊断字段，供测试/观测）。"""
    decision: BrainJudgeDecision
    schema_valid: bool
    latency_ms: float
    error: str = ""
    raw: str = ""


class BrainJudge:
    """LLM 结构化决策器。reactive / background 共用，按 mode 选 prompt。"""

    def __init__(self):
        self._persona_cache: dict | None = None

    # ── 配置 ─────────────────────────────────────────────────
    def _build_llm_config(self):
        """使用 LLM 配置（llm.json，设置→LLM），覆盖 temperature / max_tokens / timeout。"""
        from modules.LLM import LLMConfig
        from core.settings import ConfigManager
        cfg = get_brain_config()
        llm_cfg = ConfigManager.get_instance().read_llm()
        base = {
            "provider": llm_cfg.get("provider", "openai"),
            "model": llm_cfg.get("model", "gpt-4o-mini"),
            "api_key": llm_cfg.get("api_key", ""),
            "base_url": llm_cfg.get("base_url", ""),
        }
        base["temperature"] = cfg.get("judge_temperature", 0.3)
        base["max_tokens"] = 256000  # 不限制，保证 JSON 输出完整
        base["timeout"] = cfg.get("judge_timeout_seconds", 20)
        base["thinking_mode"] = False  # judge 要稳定 JSON，关闭思考模式
        return LLMConfig.from_dict(base)

    def _persona(self) -> dict:
        if self._persona_cache is None:
            self._persona_cache = _persona()
        return self._persona_cache

    def _system_prompt(self, mode: str, activity: str = "") -> str:
        persona = self._persona()
        if mode == REACTIVE:
            tpl = _REACTIVE_PROMPT
        else:
            tpl = _IDLE_PROMPT
        if not tpl:
            tpl = "你是 {name}。输出一个 JSON 决策对象。"
        return (tpl
                .replace("{name}", persona["name"])
                .replace("{traits}", persona["traits"])
                .replace("{activity}", activity or "wait"))

    def _user_prompt(self, judge_view: dict) -> str:
        return (
            "当前上下文（JSON）：\n"
            + json.dumps(judge_view, ensure_ascii=False, default=str)
            + "\n\n请输出本轮决策 JSON。"
        )

    # ── 主调用 ───────────────────────────────────────────────
    def decide(
        self,
        judge_view: dict,
        mode: str = REACTIVE,
        activity: str = "",
        *,
        mock_response: str | None = None,
    ) -> JudgeResult:
        """输出一个决策。mock_response 非空时绕过真实 LLM（测试用）。

        Returns: JudgeResult（含 decision + schema_valid + latency + error）。
        """
        import time as _t
        t0 = _t.perf_counter()
        schema_valid = False
        error = ""
        raw = ""

        try:
            if mock_response is not None:
                raw = mock_response
            else:
                raw = self._call_llm(mode, activity, judge_view)
            parsed = _parse_json(raw)
            if not isinstance(parsed, dict):
                error = "judge output not json object"
                decision = self._fallback_decision(mode, "judge_output_invalid")
            else:
                schema_valid = self._validate(parsed)
                if schema_valid:
                    parsed["mode"] = mode
                    decision = BrainJudgeDecision.from_dict(parsed)
                else:
                    # next_action 非法 → 降级 abort，避免执行未知动作
                    parsed["mode"] = mode
                    decision = BrainJudgeDecision.from_dict(parsed)
                    decision.next_action = "abort"
                    error = f"invalid next_action: {parsed.get('next_action')!r}"
        except Exception as e:
            logger.warning(f"[judge] decide error: {e}")
            error = str(e)
            decision = self._fallback_decision(mode, "judge_exception")

        latency = (_t.perf_counter() - t0) * 1000.0
        return JudgeResult(
            decision=decision,
            schema_valid=schema_valid,
            latency_ms=latency,
            error=error,
            raw=raw,
        )

    def _call_llm(self, mode: str, activity: str, judge_view: dict) -> str:
        from modules.LLM import get_llm_manager
        cfg = self._build_llm_config()
        ok, err = cfg.validate()
        if not ok:
            raise RuntimeError(f"invalid llm config: {err}")
        system = self._system_prompt(mode, activity)
        user = self._user_prompt(judge_view)
        return get_llm_manager().complete(system, user, cfg)

    # ── 校验 / 兜底 ─────────────────────────────────────────
    @staticmethod
    def _validate(parsed: dict) -> bool:
        action = str(parsed.get("next_action", "")).strip()
        return action in ACTIONS

    @staticmethod
    def _fallback_decision(mode: str, reason: str) -> BrainJudgeDecision:
        """LLM 失败时的安全决策：reactive→final_reply（让旧链路兜底）；
        background→sleep（安静等待，不浪费 LLM）。"""
        if mode == REACTIVE:
            return BrainJudgeDecision(
                mode=mode,
                next_action="final_reply",
                thought_summary=f"judge 兜底: {reason}",
                confidence=0.0,
            )
        return BrainJudgeDecision(
            mode=mode,
            next_action="sleep",
            thought_summary=f"judge 兜底: {reason}",
            confidence=0.0,
        )


# ── 单例 ─────────────────────────────────────────────────────
_judge: BrainJudge | None = None


def get_brain_judge() -> BrainJudge:
    global _judge
    if _judge is None:
        _judge = BrainJudge()
    return _judge
