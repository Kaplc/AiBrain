"""
compilation — tool 消息校验与上下文优化

外部访问：
    from modules.chat.compilation.sanitizer import sanitize_tool_pairs
"""
from .sanitizer import sanitize_tool_pairs

__all__ = [
    "sanitize_tool_pairs",
]
