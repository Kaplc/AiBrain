"""敏感信息屏蔽（T004 / FR-009）

规则优先：用正则识别明显敏感内容（密码 / token / key / cookie / 私密链接 / 私钥等）。
对每段文本产出一个 sensitivity ∈ [0,1]：
  - 命中「强敏感」模式（私钥 / 凭证 URL / 形如 key=xxx）→ 直接判定 skip，sensitivity=1.0
  - 命中「中敏感」模式（长 token / 邮箱 / 手机号 / 身份证样）→ 提升分数，但不一定 skip

mask() 返回脱敏后的文本（把敏感片段替换为 ***），供 trace 记录与可选写入。
本层只做识别与计分，是否最终 skip 由 policy 按 sensitivity 阈值决定。
"""
from __future__ import annotations

import re

# ── 强敏感：命中即应跳过（sensitivity → 1.0）────────────────
_STRONG_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),           # 私钥
    re.compile(r"https?://[^/\s:@]+:[^/\s@]+@[^\s]+"),           # 带账密凭证的 URL
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|"
               r"access[_-]?key|private[_-]?key|client[_-]?secret|"
               r"bearer|authorization)\b\s*[:=]\s*\S{4,}"),       # key=xxx / token: xxx
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),                     # AWS access key id
    re.compile(r"(?i)\bcookie\s*[:=]\s*\S{4,}"),                 # cookie 头
]

# ── 中敏感：提升分数但不一定跳过 ────────────────────────────
_MEDIUM_PATTERNS = [
    re.compile(r"(?i)\b(ghp|gho|github_pat)_[A-Za-z0-9]{16,}\b"),  # GitHub token
    re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"),                        # 40+ 字符的 token 串
    re.compile(r"\b1[3-9]\d{9}\b"),                                # 中国手机号
    re.compile(r"\b\d{15,18}[Xx]?\b"),                             # 身份证样
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),                  # 邮箱
]


def _mask_in_text(text: str, pattern: re.Pattern) -> tuple[str, int]:
    """用 *** 替换 pattern 命中片段，返回 (脱敏文本, 命中次数)。"""
    hits = [0]

    def _sub(m: re.Match) -> str:
        hits[0] += 1
        return "***"

    masked = pattern.sub(_sub, text)
    return masked, hits[0]


def analyze(text: str) -> tuple[str, float, str]:
    """分析文本敏感度。

    Returns:
        (masked_text, sensitivity, reason)
        sensitivity ∈ [0,1]：1.0 = 强敏感应跳过；中敏感按命中数累积（上限 0.8）。
    """
    if not text:
        return "", 0.0, ""

    masked = text
    strong_hits = 0
    strong_reason = ""

    for p in _STRONG_PATTERNS:
        masked, n = _mask_in_text(masked, p)
        if n:
            strong_hits += n
            strong_reason = strong_reason or p.pattern[:40]

    if strong_hits:
        return masked, 1.0, f"强敏感命中({strong_reason})"

    medium_hits = 0
    for p in _MEDIUM_PATTERNS:
        masked, n = _mask_in_text(masked, p)
        medium_hits += n

    if medium_hits:
        # 中敏感：每命中 +0.25，上限 0.8
        score = min(0.8, 0.25 * medium_hits)
        return masked, round(score, 3), f"中敏感命中 x{medium_hits}"

    return text, 0.0, ""


def is_sensitive(text: str, threshold: float = 0.6) -> bool:
    """便捷判定：sensitivity >= threshold 视为敏感。"""
    return analyze(text)[1] >= threshold


def mask(text: str) -> str:
    """便捷脱敏：返回把敏感片段替换为 *** 的文本（用于 trace）。"""
    return analyze(text)[0]
