"""Prompt Section 注册"""
from .memory import _make_step as make_memory
from .subconscious import _make_step as make_subconscious
from .self_narrative import _make_step as make_self_narrative
from .association_recall import _make_step as make_association_recall
from .internal_state import _make_step as make_internal_state


def get_all_sections():
    return [
        make_subconscious(),
        make_self_narrative(),
        make_memory(),
        make_association_recall(),
        make_internal_state(),
    ]
