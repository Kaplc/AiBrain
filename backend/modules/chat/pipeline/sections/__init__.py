"""Prompt Section 注册"""
from .memory import _make_step as make_memory


def get_all_sections():
    return [
        make_memory(),
    ]
