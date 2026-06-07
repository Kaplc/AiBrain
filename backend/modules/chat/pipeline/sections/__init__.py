"""Prompt Section 注册"""
from .chat_history import _make_step as make_chat_history
from .memory import _make_step as make_memory
from .current_msg import _make_step as make_current_msg


def get_all_sections():
    return [
        make_chat_history(),
        make_memory(),
        make_current_msg(),
    ]
