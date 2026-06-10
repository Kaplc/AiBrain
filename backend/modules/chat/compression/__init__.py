"""
compression — 后台上下文压缩模块

外部访问：
    from modules.chat.compression.context_compress import try_spawn_compress, reload_if_needed
"""
from .context_compress import try_spawn_compress, reload_if_needed

__all__ = [
    "try_spawn_compress",
    "reload_if_needed",
]
