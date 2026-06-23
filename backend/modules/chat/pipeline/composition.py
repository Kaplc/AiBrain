"""
Prompt 组合层 — 把各 section 产出的内容组织成结构化 block

设计目标（见 plan/chat-context-blocks-refactor.md）：
- 把原来「单个 system 字符串」拆成「稳定主前缀 + 多个独立上下文块」。
- 稳定块（subconscious + 固定规则）放在最前，连续多轮保持字节一致，提升 KV cache 命中。
- 动态块（self_narrative / internal_state / brain_context / skills_inject / memory / association_recall）
  顺序固定、可单独定位日志与单测，放在历史与 tool memory 之后、用户消息之前的易变尾部。
- render(provider) 对不同 provider 做确定性序列化：
    · OpenAI-compatible：直接发送多个 system block，顺序固定。
    · Anthropic：messages 数组不支持穿插 system，确定性合并成一个前缀 system。

本层只做内存拼装，不做网络请求、不落盘。
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger('chat.pipeline')

# 与 modules/LLM/stream.py 的 _OPENAI_COMPATIBLE 保持语义一致：
# 除了 anthropic，其余 provider 都走 OpenAI 兼容协议、可接受多个 system message。
_ANTHROPIC_PROVIDER = "anthropic"


def _fingerprint(content: str) -> str:
    """内容短指纹（md5 前 12 位），用于缓存对比与「哪个块变了」的排障"""
    if not content:
        return ""
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]


@dataclass
class PromptBlock:
    """单个 prompt 片段

    Attributes:
        name: block 标识（英文，全局唯一，便于日志与单测），如 subconscious / brain_context
        content: block 文本内容（含【中文标题】头，保持 LLM 可见结构）
        role: 消息角色，本次主要用于 system
        stable: 是否属于稳定前缀（subconscious 及固定规则为 True）
        order: 块序号，必须固定且可测试
        enabled: 是否参与组装
        source: 来源模块或函数，用于排障
        fingerprint: 内容摘要，便于缓存对比与调试
    """
    name: str
    content: str = ""
    role: str = "system"
    stable: bool = False
    order: int = 0
    enabled: bool = True
    source: str = ""
    fingerprint: str = ""

    def __post_init__(self):
        # 内容确定后自动算指纹（显式传入的优先）
        if not self.fingerprint:
            self.fingerprint = _fingerprint(self.content)


@dataclass
class PromptComposition:
    """一轮对话的完整 block 组合

    stable_blocks / dynamic_blocks 由 PromptPipeline.build() 填充；
    history_messages / tool_memory_messages / user_message 由 loop.py 在组装阶段挂载。
    """
    stable_blocks: list[PromptBlock] = field(default_factory=list)
    dynamic_blocks: list[PromptBlock] = field(default_factory=list)
    history_messages: list[dict] = field(default_factory=list)
    tool_memory_messages: list[dict] = field(default_factory=list)
    user_message: str = ""
    metadata: dict = field(default_factory=dict)

    # ── 写入 ──────────────────────────────────────────────
    def add_stable(self, block: PromptBlock) -> None:
        block.stable = True
        self.stable_blocks.append(block)

    def add_dynamic(self, block: PromptBlock) -> None:
        block.stable = False
        self.dynamic_blocks.append(block)

    # ── 渲染 ──────────────────────────────────────────────
    def _active(self, blocks: list[PromptBlock]) -> list[PromptBlock]:
        return [b for b in blocks if b.enabled and b.content]

    def render(self, provider: str = "") -> list[dict]:
        """为指定 provider 生成最终消息序列（固定顺序、确定性）

        组装顺序（OpenAI-compatible，保留多个独立 system block）：
            [稳定主前缀 system] + [历史] + [tool memory] + [动态上下文 system...] + [user]

        Anthropic 降级：messages 数组不支持穿插 system，把所有 system 块按序
        合并成一个前缀 system message（确定性序列化），其余保持顺序。
        """
        stable = self._active(self.stable_blocks)
        dynamic = self._active(self.dynamic_blocks)

        # ── Anthropic：确定性合并 system ──
        if provider == _ANTHROPIC_PROVIDER:
            system_text = "\n\n".join(b.content for b in (stable + dynamic) if b.content)
            msgs: list[dict] = []
            if system_text:
                msgs.append({"role": "system", "content": system_text})
            msgs.extend(self.history_messages)
            msgs.extend(self.tool_memory_messages)
            if self.user_message:
                msgs.append({"role": "user", "content": self.user_message})
            return msgs

        # ── OpenAI-compatible：多个 system block 各自独立、顺序固定 ──
        msgs = []
        for b in stable:
            msgs.append({"role": b.role or "system", "content": b.content})
        msgs.extend(self.history_messages)
        msgs.extend(self.tool_memory_messages)
        for b in dynamic:
            msgs.append({"role": b.role or "system", "content": b.content})
        if self.user_message:
            msgs.append({"role": "user", "content": self.user_message})
        return msgs

    # ── 可观测性 ──────────────────────────────────────────
    def summary(self) -> dict:
        """block 名称、顺序、长度与最终消息数，供日志定位"""
        stable = self._active(self.stable_blocks)
        dynamic = self._active(self.dynamic_blocks)
        return {
            "stable": [(b.name, b.order, len(b.content), b.fingerprint) for b in stable],
            "dynamic": [(b.name, b.order, len(b.content), b.fingerprint) for b in dynamic],
            "history_msgs": len(self.history_messages),
            "tool_memory_msgs": len(self.tool_memory_messages),
            "user_len": len(self.user_message),
            "total_msgs": len(self.render(self.metadata.get("provider", ""))),
        }
