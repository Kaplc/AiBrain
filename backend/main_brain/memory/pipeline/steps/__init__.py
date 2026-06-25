"""步骤注册中心 - 统一注册所有 store/search 步骤"""
from .store import get_all_store_steps
from .search import get_all_search_steps


def register_all_steps(engine):
    """注册所有步骤到引擎

    Args:
        engine: PipelineEngine 实例
    """
    for step in get_all_store_steps():
        engine.register_step(step)
    for step in get_all_search_steps():
        engine.register_step(step)
