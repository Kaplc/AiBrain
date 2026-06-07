"""
BaseAgent - Agent 基类
所有 Agent 继承此类，实现 run() 接口。
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Agent 基类 —— 所有 Agent 继承此接口

    用法：
        class MyAgent(BaseAgent):
            name = "my_agent"
            description = "我的 Agent"
            system_prompt = "你是..."

            def run(self, input_data, **kwargs):
                # 调 LLMManager 处理 input_data
                return result
    """

    name: str = ""
    description: str = ""
    system_prompt: str = ""
    enable_thinking: bool = True  # 默认开启 DeepSeek 思考模式

    @abstractmethod
    def run(self, input_data: Any, **kwargs) -> Any:
        """执行 Agent 的核心逻辑

        Args:
            input_data: 主要输入（文本 / 列表 / dict）
            **kwargs:
                config: LLMConfig（可选，覆盖默认配置）
                temperature: float（可选）
                max_tokens: int（可选）

        Returns:
            结构化输出（dict / list / str）
        """
        ...
