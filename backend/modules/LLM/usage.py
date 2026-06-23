"""
Usage 归一化 — 统一不同 provider 的 token usage 字段命名

不同 provider 对缓存命中的字段命名不一致，这里集中收敛成统一结构 UsageMetrics：
- prompt_cache_hit_tokens / prompt_cache_miss_tokens   （DeepSeek 等）
- cached_tokens / cache_read_input_tokens              （OpenAI 风格 / Anthropic）
- prompt_tokens_details.cached_tokens                  （OpenAI 官方）

只做字段映射与缺失推导，不做 IO；写入仍由 stream 内部的 _record_token_usage 落到现有 token_usage 表。
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _as_dict(obj: Any) -> dict:
    """把 SDK usage 对象 / 任意对象转成 dict 视图

    优先用 pydantic 的 model_dump（openai v1 SDK），再补 model_extra（DeepSeek 等扩展字段），
    最后兜底 __dict__。
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    out: dict = {}
    if hasattr(obj, "model_dump"):
        try:
            out.update(obj.model_dump())
        except Exception:
            pass
    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        out.update(extra)
    if not out and hasattr(obj, "__dict__"):
        out = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return out


def _to_int(v: Any) -> int:
    """安全转 int，None / 非数字 → 0"""
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


@dataclass
class UsageMetrics:
    """归一化后的 token 用量"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    raw_usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转成 _record_token_usage / SSE 期望的扁平 dict"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "cache_miss_tokens": self.cache_miss_tokens,
        }


class UsageNormalizer:
    """统一不同 provider 的 usage 字段"""

    @staticmethod
    def normalize(raw_usage: Any, provider: str = "") -> UsageMetrics:
        """把原始 usage 归一化成 UsageMetrics

        缺失字段记 0；若 provider 只返回 cached/hit 而无 miss，且 prompt_tokens 已知，
        则 miss = prompt_tokens - hit（结果非负时才推导）。
        """
        if raw_usage is None:
            return UsageMetrics()

        # 统一成 dict 视图作为唯一事实来源：
        # - dict 原样；SDK 对象走 model_dump()（pydantic v2，extra=allow 时含 DeepSeek 扩展字段）；
        # - 再补 model_extra；最后兜底 __dict__。
        # 不对原始对象做 getattr 兜底——MagicMock 会自动生成任意属性，污染结果。
        dv = _as_dict(raw_usage)

        def pick(*keys: str) -> Any:
            for k in keys:
                if k in dv and dv[k] is not None:
                    return dv[k]
            return None

        prompt_tokens = _to_int(pick("prompt_tokens", "input_tokens"))
        completion_tokens = _to_int(pick("completion_tokens", "output_tokens"))

        # ── 缓存命中：汇聚多种 provider 命名 ──
        cache_hit = _to_int(pick(
            "cache_hit_tokens",
            "prompt_cache_hit_tokens",
            "cached_tokens",
            "cache_read_input_tokens",
        ))

        # OpenAI 官方：prompt_tokens_details.cached_tokens
        details = pick("prompt_tokens_details")
        if not cache_hit and details is not None:
            d_dict = details if isinstance(details, dict) else _as_dict(details)
            cache_hit = _to_int(d_dict.get("cached_tokens"))

        # ── 缓存未命中 ──
        cache_miss = _to_int(pick(
            "cache_miss_tokens",
            "prompt_cache_miss_tokens",
            "cache_creation_input_tokens",
        ))

        # 推导：只有命中、没有未命中且 prompt 总量已知 → miss = prompt - hit
        if cache_hit and not cache_miss and prompt_tokens:
            derived = prompt_tokens - cache_hit
            if derived >= 0:
                cache_miss = derived

        if cache_hit or cache_miss:
            logger.debug(
                f"[llm:usage] normalized provider={provider} "
                f"prompt={prompt_tokens} completion={completion_tokens} "
                f"hit={cache_hit} miss={cache_miss}"
            )

        return UsageMetrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            raw_usage=dv,
        )
