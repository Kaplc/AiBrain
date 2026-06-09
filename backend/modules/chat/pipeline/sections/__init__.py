"""Prompt Section 注册"""
from .memory import _make_step as make_memory
from .subconscious import _make_step as make_subconscious


def get_all_sections():
    return [
        make_subconscious(),
        make_memory(),
    ]
