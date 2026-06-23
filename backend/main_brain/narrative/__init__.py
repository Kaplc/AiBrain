"""自我叙事 — 自传 / 叙事锚点 / 身份预算

外部访问：
    from main_brain.narrative import get_self_narrative, init_self_narrative, parse_json
    from main_brain.narrative.steps import register_narrative_steps
    from main_brain.narrative.prompts import NARRATIVE_SIGNIFICANCE_PROMPT, ...
"""
from .store import init_self_narrative, get_self_narrative
from .utils import parse_json
