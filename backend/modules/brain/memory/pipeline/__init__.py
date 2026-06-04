"""
Pipeline 模块 - 流水线架构入口
提供 init_pipelines() 工厂函数，在 app 启动时调用一次
"""
import logging

from .engine import PipelineEngine
from .config import get_default_config

logger = logging.getLogger('memory.pipeline')

_initialized = False


def init_pipelines() -> PipelineEngine:
    """初始化流水线引擎：注册所有步骤 + 加载配置

    在 app.py 的 create_app() 中、路由注册前调用。
    语义模型预热在前，pipeline 初始化在后。

    Returns:
        PipelineEngine 单例
    """
    global _initialized
    if _initialized:
        logger.info("[pipeline] already initialized, skip")
        return PipelineEngine.get_instance()

    engine = PipelineEngine.get_instance()

    # 1. 注册所有步骤
    from .steps import register_all_steps
    register_all_steps(engine)

    # 2. 加载默认配置（从 config.py 的 DEFAULT_CONFIG）
    config = get_default_config()

    # 3. 合并配置到引擎（将文件配置中的 enabled 状态应用到注册的步骤）
    for pipeline_name in ("store", "search"):
        steps_cfg = config.get(pipeline_name, [])
        # 校验：确保配置中的每个步骤都已注册
        validated = []
        for step_cfg in steps_cfg:
            name = step_cfg.get("name")
            step_def = engine.get_step(name)
            if step_def:
                validated.append({
                    "name": name,
                    "enabled": step_cfg.get("enabled", True),
                    "required": step_cfg.get("required", step_def.required),
                })
            else:
                logger.warning(f"[pipeline] config references unregistered step: {name}, ignoring")
        engine._pipelines[pipeline_name] = validated

    _initialized = True
    logger.info(
        f"[pipeline] initialized | "
        f"store={[s['name'] for s in engine.get_pipeline('store')]} | "
        f"search={[s['name'] for s in engine.get_pipeline('search')]}"
    )
    return engine


def get_engine() -> PipelineEngine:
    """获取引擎单例（便捷方法）"""
    return PipelineEngine.get_instance()
