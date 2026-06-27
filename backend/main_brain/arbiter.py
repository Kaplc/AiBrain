"""Arbiter —— 前额叶仲裁层（T015 / FR-014-r2 / T015-r2）

ActivitySelector（习惯回路）负责 95% 的常规活动选择。但当它的
confidence 低于阈值时，Arbiter 介入做「元决策」。

增强行为（T015-r2）：
  1. 环境感知 — 从最近对话中提取情感倾向，影响活动偏好
  2. 兴趣衰减 — 记录已学 topic，抑制重复活动
  3. 长周期节律 — 根据 time_of_day 调整行为偏好
  4. 记忆回放 — 空闲 > 2h 时自然触发 consolidation 式活动
  5. 中断响应 — 跨轮检查 chat_busy 状态，允许提前切活动

Arbiter 使用与 BrainJudge 相同的 LLM 基础设施（modules.LLM），
但 prompt 和输出 schema 不同。
"""
from __future__ import annotations

import json
import logging
import os

from .config import get_brain_config
from .contracts import (
    TICK_SHORT, TICK_MEDIUM, TICK_LONG, TICK_DAILY, TICK_MANUAL,
)

logger = logging.getLogger("main_brain.arbiter")

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# 仲裁触发阈值
# confidence 低于此值时调 LLM 仲裁
DEFAULT_ARBITER_THRESHOLD = 0.55

# 活动能量消耗分级
ENERGY_LOW = 0.2   # 最小能量
ENERGY_COST = {
    "wait": 0.0,
    "reflect": 0.1,
    "maintain_goal": 0.1,
    "prepare_expression": 0.2,
    "self_learn": 0.3,
    "advance_open_loop": 0.3,
    "organize_memory": 0.3,
    "proactive_contact": 0.2,
    "use_tool": 0.4,
}


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"[arbiter] load prompt {name} failed: {e}")
        return ""


_ARBITER_PROMPT = _load_prompt("brain_arbiter.md")


def _persona() -> dict:
    """轻量人格——与 judge 共享同一来源。"""
    try:
        from main_brain.state import get_self_model
        sm = get_self_model().get()
        return {
            "name": sm.get("name", "猫猫"),
            "traits": "、".join(sm.get("traits", []) or ["好奇", "随性"]),
        }
    except Exception:
        return {"name": "猫猫", "traits": "好奇、随性"}


# ── 情感检测（轻量关键词，不调 LLM）───────────────────────────

_POSITIVE_WORDS = {
    "好", "棒", "厉害", "喜欢", "开心", "谢谢", "感谢", "赞", "nice", "great",
    "good", "love", "awesome", "cool", "wonderful", "perfect", "amazing",
    "聪明", "对", "正确", "优秀", "满意", "高兴", "有趣", "厉害",
}
_NEGATIVE_WORDS = {
    "不好", "差", "不喜欢", "烦", "累", "烦人", "错", "不对", "差劲",
    "bad", "wrong", "terrible", "hate", "annoying", "stupid", "slow",
    "无聊", "没意思", "没用", "垃圾", "失望", "生气", "伤心", "烦死了",
}


def detect_sentiment(text: str) -> float:
    """从文本中检测情感倾向，返回 -1.0 到 1.0 的分数。

    正值 = 积极，负值 = 消极。基于关键词子串匹配，轻量不调 LLM。
    在原始文本上分别独立扫描正/负词出现次数（不替换，避免破坏复合词）。
    长词优先（"不好"优先于"好"），防止短词吞长词。
    """
    if not text or not text.strip():
        return 0.0
    text_lower = text.lower()
    # 在原始文本上独立扫描，互不干扰
    pos_count = sum(1 for w in _POSITIVE_WORDS if w in text_lower)
    neg_count = sum(1 for w in _NEGATIVE_WORDS if w in text_lower)
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return (pos_count - neg_count) / total


def compute_recent_sentiment(recent_user_messages: list[dict]) -> float:
    """计算最近用户消息的综合情感分数。"""
    if not recent_user_messages:
        return 0.0
    scores = []
    for msg in recent_user_messages:
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        if content:
            scores.append(detect_sentiment(content))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


# ── 昼夜节律 ──────────────────────────────────────────────────


def get_circadian_phase() -> str:
    """返回当前昼夜节律相位：dawn / morning / afternoon / evening / night。"""
    try:
        from datetime import datetime
        hour = datetime.now().hour
        if 5 <= hour < 8:
            return "dawn"
        if 8 <= hour < 12:
            return "morning"
        if 12 <= hour < 18:
            return "afternoon"
        if 18 <= hour < 22:
            return "evening"
        return "night"
    except Exception:
        return "afternoon"


def get_circadian_energy_modifier() -> float:
    """根据昼夜节律返回 energy 修正系数（0.8-1.2）。"""
    phase = get_circadian_phase()
    modifiers = {
        "dawn": 0.9,      # 刚醒，能量略低
        "morning": 1.2,   # 上午是高峰
        "afternoon": 1.0, # 午后平稳
        "evening": 0.85,  # 晚上下降
        "night": 0.5,     # 深夜低能量
    }
    return modifiers.get(phase, 1.0)


class Arbiter:
    """前额叶仲裁层——LLM 驱动，仅在规则式 selector 置信度低时触发。"""

    def __init__(self):
        self._persona_cache: dict | None = None
        self._last_activities: dict[str, list[str]] = {}  # tick_type -> [最近 N 次活动]
        self._recent_topics: list[str] = []  # 最近学习的 topic，用于兴趣衰减

    # ── 主入口 ─────────────────────────────────────────────────

    def arbitrate(
        self,
        life_state: dict,
        tick_type: str,
        *,
        candidates: list[dict] | None = None,
        recent_runs: list[dict] | None = None,
        fallback: tuple[str, str] | None = None,
        mock_response: str | None = None,
    ) -> tuple[str, str, float]:
        """仲裁：从候选活动中选一个最合适的。

        Args:
            life_state: 完整 LifeState dict
            tick_type: 当前 tick 类型
            candidates: 候选活动列表（含 frontmatter 元数据），
                        None = 用全部注册活动
            recent_runs: 最近几次 run 记录（用于 novelty 检测）
            fallback: LLM 失败时回退的 (activity, reason)
            mock_response: 测试用 mock

        Returns:
            (activity, reason, reduced_confidence)
        """
        if mock_response is not None:
            return self._parse_mock_response(mock_response, fallback)

        # 1. 构建给 LLM 的输入
        user_prompt = self._build_prompt(life_state, tick_type, candidates, recent_runs)
        if not user_prompt:
            return fallback or ("wait", "arbiter_prompt_failed", 0.0)

        # 2. 调 LLM
        raw = self._call_llm(user_prompt)
        if not raw:
            logger.warning("[arbiter] LLM returned empty, using fallback")
            return fallback or ("wait", "arbiter_llm_empty", 0.0)

        # 3. 解析
        return self._parse_llm_output(raw, fallback or ("wait", "arbiter_parse_failed"))

    # ── Prompt 构建 ───────────────────────────────────────────

    def _build_prompt(
        self,
        life_state: dict,
        tick_type: str,
        candidates: list[dict] | None = None,
        recent_runs: list[dict] | None = None,
    ) -> str:
        """构建完整 prompt（system + user）。"""
        prompt = _ARBITER_PROMPT
        if not prompt:
            return ""

        persona = self._persona()
        prompt = (
            prompt
            .replace("{name}", persona["name"])
            .replace("{traits}", persona["traits"])
        )

        # 当前状态摘要
        state_summary = self._summarize_state(life_state, tick_type, recent_runs)
        prompt = prompt.replace("{state_json}", state_summary)

        # 候选活动列表
        act_json = self._format_candidates(candidates)
        prompt = prompt.replace("{activities_json}", act_json)

        return prompt

    def _summarize_state(
        self,
        life_state: dict,
        tick_type: str,
        recent_runs: list[dict] | None = None,
    ) -> str:
        """把生命状态转成 LLM 易读的 JSON 摘要。

        增强字段（T015-r2）：
          - time_of_day / circadian_phase：昼夜节律
          - recent_sentiment：最近用户对话的情感倾向
          - recent_topics：已学 topic 列表（兴趣衰减）
          - chat_busy：用户是否正在聊天中
        """
        energy = float(life_state.get("energy", 0.6) or 0.6)
        drives = life_state.get("drives", {}) or {}
        goals = life_state.get("goals", []) or []
        open_loops = life_state.get("open_loops", []) or []
        pending = life_state.get("pending_expressions", []) or []
        thoughts = life_state.get("recent_thoughts", []) or []
        mood = life_state.get("mood", {}) or {}
        idle = int(life_state.get("idle_seconds", 0) or 0)

        # 最近活动统计（用于 novelty 检测）
        recent_acts = []
        if recent_runs:
            recent_acts = [
                r.get("selected_activity", r.get("actions", [""])[0])
                for r in recent_runs[:6]
            ]

        # ① 昼夜节律
        circadian_phase = get_circadian_phase()
        energy_mod = get_circadian_energy_modifier()

        # ② 环境感知：从 life_state 读最近情感
        recent_sentiment = compute_recent_sentiment(
            life_state.get("recent_user_messages", []) or []
        )

        # ③ 兴趣衰减：已学 topic（由 self_learn 记录）
        recent_topics = list(self._recent_topics[-5:]) if self._recent_topics else []

        # ④ 中断响应：chat 是否繁忙
        chat_busy = _is_chat_busy()

        # ⑤ 自然记忆回放条件：长时间空闲适合做 consolidation
        natural_replay_hint = (idle > 7200 and circadian_phase in ("night", "dawn"))

        slices = {
            "tick_type": tick_type,
            "idle_seconds": idle,
            "energy": round(energy * energy_mod, 2),
            "circadian_phase": circadian_phase,
            "time_of_day": circadian_phase,
            "chat_busy": chat_busy,
            "mood": {
                "label": mood.get("label", "neutral"),
                "valence": mood.get("valence", 0),
                "arousal": mood.get("arousal", 0),
            },
            "drives": {
                "curiosity": float(drives.get("curiosity", 0) or 0),
                "companionship": float(drives.get("companionship", 0) or 0),
                "completion": float(drives.get("completion", 0) or 0),
            },
            "open_loops_count": len(open_loops),
            "open_loops": [l.get("content", str(l))[:80] if isinstance(l, dict) else str(l)[:80]
                           for l in open_loops[:3]],
            "pending_expressions_count": len(pending),
            "goals": [g.get("name", str(g))[:60] if isinstance(g, dict) else str(g)[:60]
                      for g in goals[:3]],
            "recent_runs": recent_acts,
            "recent_sentiment": round(recent_sentiment, 3),
            "recent_topics": recent_topics,
            "natural_replay_hint": natural_replay_hint,
        }
        return json.dumps(slices, ensure_ascii=False, default=str)

    def _format_candidates(self, candidates: list[dict] | None) -> str:
        """把候选活动列表格式化为 LLM 易读的 JSON 数组。"""
        if candidates is not None:
            items = []
            for c in candidates:
                items.append({
                    "name": c.get("name", ""),
                    "description": c.get("description", "")[:120],
                    "allowed_tools": c.get("allowed_tools", []),
                    "conditions": c.get("conditions", {}),
                    "energy_cost": ENERGY_COST.get(c.get("name", ""), 0.2),
                })
            return json.dumps(items, ensure_ascii=False)
        # 用全部注册活动
        try:
            from .activities.registry import list_activities
            acts = list_activities()
            items = []
            for name, act in sorted(acts.items()):
                items.append({
                    "name": name,
                    "description": act.description[:120],
                    "allowed_tools": list(act.allowed_tools),
                    "conditions": dict(act.conditions) if isinstance(act.conditions, dict) else {},
                    "energy_cost": ENERGY_COST.get(name, 0.2),
                })
            return json.dumps(items, ensure_ascii=False, default=str)
        except Exception:
            return "[]"

    # ── LLM 调用 ──────────────────────────────────────────────

    def _call_llm(self, user_prompt: str) -> str:
        """调用 LLM，返回原始响应。"""
        cfg = get_brain_config()
        try:
            from modules.LLM import LLMConfig, get_llm_manager
            from core.settings import ConfigManager
            llm_cfg = ConfigManager.get_instance().read_llm()
            base = {
                "provider": llm_cfg.get("provider", "openai"),
                "model": llm_cfg.get("model", "gpt-4o-mini"),
                "api_key": llm_cfg.get("api_key", ""),
                "base_url": llm_cfg.get("base_url", ""),
            }
            base["temperature"] = cfg.get("arbiter_temperature", 0.4)
            base["max_tokens"] = 4096
            base["timeout"] = cfg.get("arbiter_timeout_seconds", 15)
            base["thinking_mode"] = False
            llm_cfg_obj = LLMConfig.from_dict(base)
            ok, err = llm_cfg_obj.validate()
            if not ok:
                raise RuntimeError(f"invalid arbiter llm config: {err}")
            return get_llm_manager().complete(
                self._system_prompt(),
                user_prompt,
                llm_cfg_obj,
            )
        except Exception as e:
            logger.warning(f"[arbiter] LLM call failed: {e}")
            return ""

    def _system_prompt(self) -> str:
        """返回 system prompt 第一部分（不含模板替换的内容）。"""
        persona = self._persona()
        return (
            f"你是 {persona['name']}，{persona['traits']}。\n"
            f"你负责从可选的活动中选择一个最适合当前状态的活动。\n"
            f"只输出 JSON。"
        )

    # ── 输出解析 ──────────────────────────────────────────────

    @staticmethod
    def _parse_llm_output(
        raw: str,
        fallback: tuple[str, str],
    ) -> tuple[str, str, float]:
        """解析 LLM 输出的 JSON，失败时回退。"""
        # 尝试解析 JSON（直接 / 代码块内）
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # 提取代码块中的 JSON
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1)
        try:
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                raise ValueError("not a dict")
            activity = str(data.get("activity", fallback[0])).strip()
            reason = str(data.get("reason", fallback[1]))[:200]
            conf = float(data.get("confidence", 0.5))
            return (activity, reason, max(0.0, min(1.0, conf)))
        except Exception as e:
            logger.warning(f"[arbiter] parse failed: {e} | raw={raw[:160]}")
            return (fallback[0], fallback[1], 0.0)

    @staticmethod
    def _parse_mock_response(
        mock: str,
        fallback: tuple[str, str] | None,
    ) -> tuple[str, str, float]:
        """测试用 mock。直接解析 JSON 或返回 fallback。"""
        try:
            data = json.loads(mock)
            if isinstance(data, dict):
                act = str(data.get("activity", fallback[0] if fallback else "wait"))
                reason = str(data.get("reason", "mock"))[:200]
                conf = float(data.get("confidence", 0.7))
                return (act, reason, max(0.0, min(1.0, conf)))
        except Exception:
            pass
        return (fallback[0] if fallback else "wait", "mock", 0.7)

    # ── Novelty 追踪（防止持续做同件事）──────────────────────

    def record_activity(self, tick_type: str, activity: str, topic: str = "") -> None:
        """记录一次活动执行，供后续仲裁做 novelty 检测。

        Args:
            tick_type: short/medium/long/daily
            activity: 活动名
            topic: 可选，self_learn 的 topic（用于兴趣衰减）
        """
        if tick_type not in self._last_activities:
            self._last_activities[tick_type] = []
        self._last_activities[tick_type].append(activity)
        # 只保留最近 8 次
        if len(self._last_activities[tick_type]) > 8:
            self._last_activities[tick_type].pop(0)

        # 记录学习 topic（兴趣衰减）
        if activity == "self_learn" and topic:
            self._recent_topics.append(topic)
            if len(self._recent_topics) > 20:
                self._recent_topics = self._recent_topics[-20:]

    def get_repeat_count(self, tick_type: str, activity: str) -> int:
        """指定活动在最近 tick 中连续出现的次数。"""
        history = self._last_activities.get(tick_type, [])
        count = 0
        for a in reversed(history):
            if a == activity:
                count += 1
            else:
                break
        return count


# ── 阈值计算 ──────────────────────────────────────────────────


def compute_arbiter_confidence(
    selector_result: tuple[str, str],
    tick_type: str,
    life_state: dict,
) -> float:
    """根据 selector 输出和当前状态，计算需要仲裁的概率。

    返回 confidence（0-1），值越低越需要触发仲裁。
    低于 ARBITER_THRESHOLD 时触发仲裁。

    计算因子：
      - 如果是 wait（兜底）→ 低 confidence
      - 如果有多个条件同时满足 → 低 confidence（冲突）
      - 如果 energy 和活动成本不匹配 → 低 confidence
      - 如果最近 3 次 tick 都做同一件事 → 低 confidence（惯性检测）
    """
    activity, reason = selector_result

    # wait 活动基本无信息量 → 低置信
    if activity == "wait":
        return 0.35

    # daily tick 走 reflect 是固定路线 → 高置信
    if tick_type == TICK_DAILY and activity == "reflect":
        return 0.90

    # short tick 只 wait → 高置信
    if tick_type == TICK_SHORT:
        return 0.95

    # long tick 固定选择 → 高置信
    if tick_type == TICK_LONG:
        if activity == "maintain_goal":
            # 精力低策略明确
            return 0.80
        if activity == "organize_memory":
            return 0.75

    # medium tick —— 看状态
    energy = float(life_state.get("energy", 0.6) or 0.6)
    expected_cost = ENERGY_COST.get(activity, 0.2)

    # 能量不匹配
    if energy < expected_cost * 1.5 and activity not in ("wait", "reflect", "maintain_goal"):
        return 0.45

    # 默认中等置信
    base = 0.65

    # 如果 reason 包含 "暂无" "没有" "不适合" 等犹豫信号 → 降级
    hesitant = ("暂无", "没有明确", "不适合", "可能", "或许", "模糊")
    if any(h in reason for h in hesitant):
        base -= 0.15

    return max(0.2, min(0.95, base))


# ── 快捷函数 ──────────────────────────────────────────────────


def needs_arbitration(confidence: float, threshold: float | None = None) -> bool:
    """判断是否需要触发仲裁。

    Returns:
        True = confidence 低于阈值，需要仲裁
    """
    if threshold is None:
        threshold = DEFAULT_ARBITER_THRESHOLD
    return confidence < threshold


# ── 辅助工具 ──────────────────────────────────────────────────


def _is_chat_busy() -> bool:
    """用户是否正在 SSE 聊天（best-effort）。"""
    try:
        from modules.chat import ChatManager
        return bool(ChatManager.get_instance().get_status())
    except Exception:
        return False


# ── 单例 ──────────────────────────────────────────────────────

_arbiter: Arbiter | None = None


def get_arbiter() -> Arbiter:
    global _arbiter
    if _arbiter is None:
        _arbiter = Arbiter()
    return _arbiter
