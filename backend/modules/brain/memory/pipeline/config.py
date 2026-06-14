"""
PipelineConfig - 流水线配置定义与校验
DEFAULT_CONFIG 是单数据源，修改配置直接编辑此文件后重启后端。
无外部 JSON 配置文件。（运行时 GET/PUT API 修改仅影响内存，重启恢复为 DEFAULT_CONFIG）
"""
import logging
from typing import Optional

logger = logging.getLogger('memory.pipeline')

# ── 默认流水线拓扑（单数据源）─────────────────────────────────
# 修改配置：编辑下方数组中的顺序、enabled、required 值，然后重启后端。
# name 必须与 steps/store/ 或 steps/search/ 中的 _make_step() name 一致。
# required=True 的步骤不可禁用。

DEFAULT_CONFIG = {
    "store": [
        {"name": "encoder", "enabled": True, "required": False},
        {"name": "vector_store", "enabled": True, "required": True},
        {"name": "entity_extract", "enabled": True, "required": False},
        {"name": "graph_link", "enabled": True, "required": False},
        {"name": "narrative_significance", "enabled": True, "required": False},
    ],
    "search": [
        {"name": "vector_search", "enabled": True, "required": True},
        {"name": "graph_recall", "enabled": True, "required": False},
        {"name": "narrative_warmth", "enabled": True, "required": False},
    ],
}


def get_default_config() -> dict:
    """返回 DEFAULT_CONFIG 的深拷贝"""
    import json
    return json.loads(json.dumps(DEFAULT_CONFIG))


def validate_update(pipeline_name: str, steps: list[dict], registry: dict) -> Optional[str]:
    """校验流水线更新请求，返回错误信息或 None（校验通过）

    校验规则：
    1. 未注册的 step name → 拒绝
    2. 同一 pipeline 中重复 step name → 拒绝
    3. required 步骤设置 enabled=false → 拒绝
    4. 步骤不属于该 pipeline → 拒绝

    Args:
        pipeline_name: "store" 或 "search"
        steps: 请求中的步骤列表
        registry: 引擎中已注册的步骤 {name: StepDef}

    Returns:
        错误信息字符串，None 表示校验通过
    """
    seen_names = set()

    for step_cfg in steps:
        name = step_cfg.get("name", "")
        if not name:
            return "步骤名称不能为空"

        # 规则1: 检查是否已注册
        if name not in registry:
            return f"未注册的步骤: '{name}'"

        # 规则2: 检查重复
        if name in seen_names:
            return f"重复的步骤: '{name}'"
        seen_names.add(name)

        # 规则3: required 步骤不可禁用
        step_def = registry[name]
        if step_def.required and step_cfg.get("enabled") is False:
            return f"强制步骤 '{name}' 不可禁用"

        # 规则4: 检查步骤是否属于该 pipeline
        if step_def.pipeline != pipeline_name:
            return f"步骤 '{name}' 不属于 {pipeline_name} 流水线（属于 {step_def.pipeline}）"

    return None
