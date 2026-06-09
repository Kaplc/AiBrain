"""
ToolRegistry — 工具注册表单例

管理 LLM 可调用的工具（function calling），提供注册/查询/执行/Schema 导出接口。

外部访问：
    from modules.LLM.tools import get_tool_registry
    reg = get_tool_registry()
    reg.register(tool_def)
    schemas = reg.get_openai_schemas()
    result = reg.execute("memory_search", {"query": "..."})
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    parameters: dict          # OpenAI JSON Schema 格式
    fn: Callable[..., Any]    # 执行函数
    enabled: bool = True


_INSTANCE: Optional['ToolRegistry'] = None
_INSTANCE_LOCK = threading.Lock()


class ToolRegistry:
    """工具注册表单例"""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        global _INSTANCE
        if _INSTANCE is None:
            with _INSTANCE_LOCK:
                if _INSTANCE is None:
                    _INSTANCE = cls()
        return _INSTANCE

    def register(self, tool: ToolDef) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        logger.info(f"[tools] registered: {tool.name}")

    def unregister(self, name: str) -> None:
        """注销工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolDef]:
        """获取所有已注册工具"""
        return list(self._tools.values())

    def get_openai_schemas(self, tool_names: list[str] | None = None) -> list[dict]:
        """返回 OpenAI function calling 格式的工具列表

        Args:
            tool_names: 只返回指定名称的工具，None 返回全部

        Returns:
            OpenAI 格式的工具 schema 列表
        """
        tools = self._tools.values()
        if tool_names is not None:
            tools = [t for t in tools if t.name in tool_names]
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            }
            for t in tools
            if t.enabled
        ]

    def execute(self, name: str, args: dict) -> str:
        """执行工具，返回字符串结果。异常不会抛出，而是返回错误信息。

        Args:
            name: 工具名
            args: 参数字典

        Returns:
            工具执行结果（字符串）
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: tool '{name}' not found"
        try:
            result = tool.fn(**args)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"[tools] {name} execution failed: {e}")
            return f"Error: {e}"


def get_tool_registry() -> ToolRegistry:
    """获取 ToolRegistry 单例"""
    return ToolRegistry.get_instance()
