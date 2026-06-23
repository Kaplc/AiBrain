"""
PromptContext — prompt 构造上下文
各 Section 通过此对象传递数据、产出独立 PromptBlock（稳定块 / 动态块）

本对象只负责「收集 block」，最终组装由 PromptPipeline.build() 取出 stable/dynamic
块交给 PromptComposition，再由 loop.py 挂载历史与用户消息后 render。
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .composition import PromptBlock


@dataclass
class PromptContext:
    """prompt 构造上下文"""
    # 输入
    user_message: str = ""           # 当前用户消息
    system_persona: str = ""         # 人设
    work_memory: dict = field(default_factory=dict)  # {input: [...], package: {query, results}}

    # 输出（Section 按序追加，分稳定块 / 动态块）
    stable_blocks: list[PromptBlock] = field(default_factory=list)
    dynamic_blocks: list[PromptBlock] = field(default_factory=list)

    # 中间数据
    metadata: dict = field(default_factory=dict)

    # 内部：递增序号，保证块顺序稳定、可测试、可复现
    _order_counter: int = 0

    def _next_order(self) -> int:
        self._order_counter += 1
        return self._order_counter

    # ── 稳定主前缀（subconscious + 固定规则）──
    def add_stable(self, name: str, content: str, title: str = "", source: str = "") -> None:
        """追加一个稳定块。content 前置【title】头以保持 LLM 可见结构"""
        if not content:
            return
        header = title or name
        text = f"【{header}】\n{content}" if header else content
        self.stable_blocks.append(PromptBlock(
            name=name, content=text, role="system",
            stable=True, order=self._next_order(), source=source or name,
        ))

    # ── 动态上下文块（每轮可变，顺序固定）──
    def add_block(self, name: str, content: str, title: str = "", source: str = "") -> None:
        """追加一个动态块"""
        if not content:
            return
        header = title or name
        text = f"【{header}】\n{content}" if header else content
        self.dynamic_blocks.append(PromptBlock(
            name=name, content=text, role="system",
            stable=False, order=self._next_order(), source=source or name,
        ))

    def add_section(self, title: str, content: str) -> None:
        """旧接口兼容：作为动态块追加（dormant sections 仍可用）"""
        self.add_block(title, content, title=title)
