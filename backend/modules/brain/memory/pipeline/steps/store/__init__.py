"""Store 步骤注册"""
from .encoder import _make_step as make_encoder
from .vector_store import _make_step as make_vector_store
from .entity_extract import _make_step as make_entity_extract
from .graph_link import _make_step as make_graph_link


def get_all_store_steps():
    """返回所有 store 步骤的 StepDef 列表"""
    return [
        make_encoder(),
        make_vector_store(),
        make_entity_extract(),
        make_graph_link(),
    ]
