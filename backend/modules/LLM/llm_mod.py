"""
LLM 模块 - 单例入口

LLMManager 是单例，外部用 LLMManager.get_instance() 获取。
模块本身只做"发请求拿响应"，不构造 prompt。

为什么单例？
- 项目约定：每个模块代码放在单独文件夹，模块做成单例模式，方便外部直接访问
- 实际作用：避免每个调用方重复 import 函数路径，统一入口
"""
from __future__ import annotations
import logging
from typing import Iterator

from .config import LLMConfig, SUPPORTED_PROVIDERS
from .stream import call_llm_stream, call_llm_sync, call_llm_nonstream

logger = logging.getLogger(__name__)


# ── LLMManager 单例 ────────────────────────────────────────
class LLMManager:
    """LLM 模块单例入口 —— 只做基本请求/响应

    使用：
        mgr = LLMManager.get_instance()
        cfg = LLMConfig.from_settings()  # 或自己构造
        for chunk in mgr.stream("sys", "user", cfg):
            print(chunk["content"], end="")

    不做：
    - prompt 模板（系统提示、人物设定、记忆注入都是调用方负责）
    - 记忆存取
    - 多轮对话上下文管理
    """
    _instance = "LLMManager"

    def __init__(self):
        # 轻量构造，不做 IO
        pass

    @classmethod
    def get_instance(cls) -> "LLMManager":
        if cls._instance is None or not isinstance(cls._instance, cls):
            cls._instance = cls()
        return cls._instance

    # ── 流式调用 ─────────────────────────────────────────
    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
        source: str = 'chat',
    ) -> Iterator[dict]:
        """流式 LLM 调用（system + user 双参数版）"""
        return call_llm_stream(system_prompt, user_prompt, config, source=source)

    def stream_messages(
        self,
        messages: list[dict],
        config: LLMConfig,
        source: str = 'chat',
    ) -> Iterator[dict]:
        """流式 LLM 调用（直接传 messages 数组）"""
        return call_llm_stream(config=config, messages=messages, source=source)

    # ── 非流式 ─────────────────────────────────────────
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        config: LLMConfig,
    ) -> str:
        """一次性返回完整文本（system + user 双参数版）"""
        return call_llm_sync(system_prompt, user_prompt, config)

    def complete_messages(
        self,
        messages: list[dict],
        config: LLMConfig,
    ) -> str:
        """一次性返回完整文本（直接传 messages 数组）"""
        return call_llm_sync(config=config, messages=messages)

    def complete_with_tools(
        self,
        messages: list[dict],
        config: LLMConfig,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict:
        """非流式调用 + 工具调用支持

        Returns:
            {"content": str, "tool_calls": [...]}  — tool_calls 可能为空
        """
        return call_llm_nonstream(
            config=config,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )

    # ── 配置加载快捷方法 ─────────────────────────────────
    def load_config_from_mem0(self) -> LLMConfig:
        """从 ~/.aibrain/config/mem0.json 读 LLM 配置（兼容旧路径）"""
        return LLMConfig.from_settings()

    # ── 静态信息 ─────────────────────────────────────────
    @staticmethod
    def supported_providers() -> tuple[str, ...]:
        return SUPPORTED_PROVIDERS


# ── 便利函数（让 from modules.LLM import call_llm_stream 也能工作） ──
def get_llm_manager() -> LLMManager:
    """等价于 LLMManager.get_instance()"""
    return LLMManager.get_instance()
