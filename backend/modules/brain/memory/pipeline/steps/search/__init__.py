"""Search 步骤注册"""
from .vector_search import _make_step as make_vector_search
from .event_recall import _make_step as make_event_recall
from .graph_recall import _make_step as make_graph_recall
from .time_decay import _make_step as make_time_decay


def get_all_search_steps():
    """返回所有 search 步骤的 StepDef 列表"""
    return [
        make_vector_search(),
        make_event_recall(),
        make_graph_recall(),
        make_time_decay(),
    ]
