"""Store 步骤注册"""
from .episodic_merge import _make_step as make_episodic_merge
from .encoder import _make_step as make_encoder
from .vector_store import _make_step as make_vector_store
from .scene_link import _make_step as make_scene_link


def get_all_store_steps():
    """返回所有 store 步骤的 StepDef 列表"""
    return [
        make_episodic_merge(),
        make_encoder(),
        make_vector_store(),
        make_scene_link(),
    ]
