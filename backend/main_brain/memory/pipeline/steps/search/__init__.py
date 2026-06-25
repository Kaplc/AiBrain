"""Search 步骤注册"""
from .vector_search import _make_step as make_vector_search
from .scene_recall import _make_step as make_scene_recall


def get_all_search_steps():
    """返回所有 search 步骤的 StepDef 列表"""
    return [
        make_vector_search(),
        make_scene_recall(),
    ]
