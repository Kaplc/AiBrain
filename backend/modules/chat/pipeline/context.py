"""
PromptContext — prompt 构造上下文
各 Section 通过此对象传递数据、拼接 prompt
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContext:
    """prompt 构造上下文"""
    # 输入
    user_message: str = ""           # 当前用户消息
    system_persona: str = ""         # 人设
    work_memory: dict = field(default_factory=dict)  # {input: [{seq,content,time}], package: {query, results}}

    # 输出（Section 按序追加）
    parts: list[str] = field(default_factory=list)

    # 中间数据
    metadata: dict = field(default_factory=dict)

    def add_section(self, title: str, content: str):
        """添加一个 prompt 片段"""
        if content:
            self.parts.append(f"【{title}】\n{content}")

    def build(self) -> str:
        """拼接所有片段为最终 prompt"""
        return "\n\n".join(self.parts)
