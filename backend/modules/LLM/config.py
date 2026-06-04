"""
LLM 调用配置 dataclass

设计为不可变值对象 —— 调用方传入配置，stream 模块按配置选择 provider。
这样 LLM 模块本身不持有全局状态，单例只做"接口聚合"，不做"配置存储"。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Provider 默认参数 ─────────────────────────────────────────
# 当用户没填 model / base_url 时，按 provider 给一个合理默认。
# 不强行覆盖用户已填的值。
_PROVIDER_DEFAULTS = {
    "openai":     {"model": "gpt-4o-mini",                  "base_url": ""},
    "anthropic":  {"model": "claude-sonnet-4-20250514",     "base_url": ""},
    "deepseek":   {"model": "deepseek-chat",                "base_url": "https://api.deepseek.com/v1"},
    "gemini":     {"model": "gemini-2.0-flash",             "base_url": ""},
    "groq":       {"model": "llama-3.3-70b-versatile",      "base_url": ""},
    "ollama":     {"model": "qwen2.5:7b",                   "base_url": "http://localhost:11434/v1"},
    "lmstudio":   {"model": "local-model",                  "base_url": "http://localhost:1234/v1"},
    "together":   {"model": "meta-llama/Llama-3-70b",       "base_url": ""},
    "minimax":    {"model": "MiniMax-M2.7",            "base_url": "https://api.minimaxi.com/v1"},
}


# 跟现有 modules.brain.mem0_adapter 保持一致的 provider 列表
SUPPORTED_PROVIDERS = tuple(_PROVIDER_DEFAULTS.keys())


@dataclass(frozen=True)
class LLMConfig:
    """LLM 调用配置（不可变）"""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: int = 60

    # ── 工厂方法 ─────────────────────────────────────────
    @classmethod
    def from_dict(cls, data: dict) -> "LLMConfig":
        """从 dict 构造（容忍缺字段）"""
        provider = (data.get("provider") or data.get("llm_provider") or "openai").lower()
        model = data.get("model") or data.get("llm_model") or ""
        api_key = data.get("api_key", "")
        base_url = data.get("base_url", "")
        temperature = float(data.get("temperature", 0.7))
        max_tokens = int(data.get("max_tokens", 1024))
        timeout = int(data.get("timeout", 60))

        # 缺省值用 provider 默认填充
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        if not model:
            model = defaults.get("model", "gpt-4o-mini")
        if not base_url:
            base_url = defaults.get("base_url", "")

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    @classmethod
    def from_mem0_config(cls) -> "LLMConfig":
        """兼容旧路径：~/.aibrain/config/mem0.json"""
        from core.settings import ConfigManager
        cfg = ConfigManager.get_instance().read_mem0()
        return cls.from_dict(cfg)

    # ── 校验 ─────────────────────────────────────────
    def validate(self) -> tuple[bool, str]:
        """返回 (ok, error_message)"""
        if self.provider not in _PROVIDER_DEFAULTS:
            return False, f"unsupported provider: {self.provider}（支持：{', '.join(SUPPORTED_PROVIDERS)}）"
        if not self.model:
            return False, "model 不能为空"
        if self.temperature < 0 or self.temperature > 2:
            return False, "temperature 应在 0~2 之间"
        if self.max_tokens < 1 or self.max_tokens > 32000:
            return False, "max_tokens 应在 1~32000 之间"
        # 本地 provider 允许空 api_key（其它检查通过后）
        if self.provider in ("ollama", "lmstudio"):
            return True, ""
        if not self.api_key:
            return False, f"provider '{self.provider}' 需要 api_key"
        return True, ""

    # ── 序列化 ─────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    def to_safe_dict(self) -> dict:
        """导出时脱敏 api_key"""
        d = self.to_dict()
        if d.get("api_key"):
            d["api_key"] = d["api_key"][:4] + "***" + d["api_key"][-4:] if len(d["api_key"]) > 8 else "***"
        return d
