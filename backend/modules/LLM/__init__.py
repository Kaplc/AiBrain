"""
LLM 能力模块 —— 只负责"发请求拿响应"

外部访问：
    from modules.LLM import get_llm_manager, LLMConfig, call_llm_stream, call_llm_sync

子模块：
    .config    - LLMConfig dataclass + provider 默认值
    .stream    - call_llm_stream 统一 provider 分发
    .llm_mod   - LLMManager 单例入口

不做的事：
- 不构造 system prompt / 不注入记忆 / 不做 prompt 模板
  （那是调用方 / feature 模块的事，比如 modules.chat.agent_loop）
- 不做记忆存取
- 不持有任何全局状态（除了单例本身）

依赖：openai（必需），anthropic（可选，Anthropic provider 才需要）。
"""
from .config import LLMConfig, SUPPORTED_PROVIDERS
from .stream import call_llm_stream, call_llm_sync
from .llm_mod import LLMManager, get_llm_manager

__all__ = [
    # 配置
    "LLMConfig",
    "SUPPORTED_PROVIDERS",
    # Stream
    "call_llm_stream",
    "call_llm_sync",
    # 单例
    "LLMManager",
    "get_llm_manager",
]
