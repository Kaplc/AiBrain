"""
PipelineContext - 流水线上下文，在步骤间传递数据
每个请求创建独立的 PipelineContext 实例，线程安全
"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PipelineContext:
    """流水线上下文：所有步骤通过此对象共享数据

    Attributes:
        input_data: 原始输入（text / query）
        metadata: 附加元数据
        output: 最终结果
        intermediate: 步骤间共享数据 {step_name: step_output}
        step_results: 步骤执行记录 {step_name: {duration, status, error}}
        aborted: 是否中止
    """
    input_data: Any
    metadata: dict = field(default_factory=dict)
    output: Any = None
    intermediate: dict = field(default_factory=dict)
    step_results: dict = field(default_factory=dict)
    aborted: bool = False


@dataclass
class StepDef:
    """步骤定义：描述流水线中的一个处理阶段

    Attributes:
        name: 唯一标识符
        description: 人类可读描述
        execute: 执行函数 fn(ctx: PipelineContext) -> None
        enabled: 是否启用
        required: 强制步骤不可禁用
        pipeline: 所属流水线 "store" | "search"
        timeout: 执行超时（秒）
        on_start: 执行前钩子（可选）
        on_error: 错误钩子（可选）
        on_finish: 完成钩子（可选）
    """
    name: str
    description: str
    execute: Callable
    enabled: bool = True
    required: bool = False
    pipeline: str = "store"
    timeout: float = 30.0

    # 可选生命周期钩子
    on_start: Callable = None
    on_error: Callable = None
    on_finish: Callable = None
