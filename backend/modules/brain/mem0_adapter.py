"""
mem0 适配层 - 配置并初始化 mem0 Memory 客户端
配置文件：~/.aibrain/config/mem0.json（首次启动自动创建）

支持的 LLM 提供商：openai, anthropic, gemini, deepseek, groq,
  ollama, lmstudio, together, xai, azure_openai, aws_bedrock 等

Embedding 模型强制使用本地 models/bge-m3/，禁止从网络下载。
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

_client = None

# 项目根目录（本文件在 backend/modules/brain/，向上3级到根目录）
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

# 本地 BGE-M3 模型的项目相对路径（相对于本文件位置）
# 本文件在 backend/modules/brain/mem0_adapter.py
# 向上3级到项目根目录: backend -> AiBrain -> models/bge-m3
_LOCAL_MODEL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "bge-m3")
)

# 检查本地模型必需的文件
_REQUIRED_MODEL_FILES = ("config.json", "pytorch_model.bin")

# 各 provider 对应的 API Key 环境变量名和默认模型
_PROVIDER_DEFAULTS = {
    "openai": {"env_key": "OPENAI_API_KEY", "model": "gpt-4o-mini"},
    "anthropic": {"env_key": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-20250514"},
    "gemini": {"env_key": "GEMINI_API_KEY", "model": "gemini-2.0-flash"},
    "deepseek": {"env_key": "DEEPSEEK_API_KEY", "model": "deepseek-chat"},
    "groq": {"env_key": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile"},
    "ollama": {"env_key": "", "model": "qwen2.5:7b"},
    "lmstudio": {"env_key": "", "model": "local-model"},
    "together": {"env_key": "TOGETHER_API_KEY", "model": "meta-llama/Llama-3-70b-chat-hf"},
    "xai": {"env_key": "XAI_API_KEY", "model": "grok-3-mini-fast"},
}


def _get_config_path():
    """获取配置文件路径：~/.aibrain/config/mem0.json"""
    return os.path.join(os.path.expanduser("~"), ".aibrain", "config", "mem0.json")


def _ensure_config_file():
    """检查配置文件是否存在，不存在则创建默认模板"""
    config_path = _get_config_path()
    config_dir = os.path.dirname(config_path)

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    if not os.path.exists(config_path):
        default_config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "api_key": "",
            "base_url": "",
            "collection_name": "mem0_memories"
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.info(f"Created default config: {config_path}")

    return config_path


def load_mem0_config():
    """读取 mem0 配置文件"""
    config_path = _ensure_config_file()
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_mem0_config(config_data):
    """保存 mem0 配置文件"""
    config_path = _get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def _check_local_model():
    """检查本地 BGE-M3 模型是否存在，不存在则报错（禁止网络下载）"""
    if not os.path.isdir(_LOCAL_MODEL_PATH):
        logger.error(
            f"[禁止网络下载] 本地 Embedding 模型不存在: {_LOCAL_MODEL_PATH}\n"
            f"  请将 BGE-M3 模型放到该目录下。\n"
            f"  必需文件: {', '.join(_REQUIRED_MODEL_FILES)}"
        )
        raise RuntimeError(
            f"本地 BGE-M3 模型缺失: {_LOCAL_MODEL_PATH}\n"
            f"必需文件: {', '.join(_REQUIRED_MODEL_FILES)}\n"
            f"本项目不允许从网络下载模型。"
        )
    missing = [f for f in _REQUIRED_MODEL_FILES if not os.path.exists(os.path.join(_LOCAL_MODEL_PATH, f))]
    if missing:
        logger.error(
            f"[禁止网络下载] 本地模型文件不完整: {_LOCAL_MODEL_PATH}\n"
            f"  缺少文件: {', '.join(missing)}"
        )
        raise RuntimeError(
            f"本地 BGE-M3 模型不完整，缺少: {', '.join(missing)}\n"
            f"路径: {_LOCAL_MODEL_PATH}"
        )
    logger.info(f"使用本地 Embedding 模型: {_LOCAL_MODEL_PATH}")


def get_mem0_client():
    """单例模式获取 mem0 客户端"""
    global _client
    if _client is None:
        _client = _create_client()
    return _client


def reset_mem0_client():
    """重置客户端（配置变更后调用）"""
    global _client
    _client = None


def _create_client():
    """创建 mem0 客户端，使用本地 BGE-M3 Embedding + 现有 Qdrant"""
    # 先检查本地模型是否存在（禁止网络下载）
    _check_local_model()

    from mem0 import Memory
    from brain_mcp.config import settings as brain_settings

    cfg = load_mem0_config()
    provider = cfg.get("llm_provider", "openai").lower()

    # 获取 API Key：优先配置文件 > 环境变量
    api_key = cfg.get("api_key", "")
    if not api_key and provider in _PROVIDER_DEFAULTS:
        env_name = _PROVIDER_DEFAULTS[provider]["env_key"]
        if env_name:
            api_key = os.environ.get(env_name, "")

    if not api_key and provider != "ollama":
        raise RuntimeError(
            f"缺少 {provider} 的 API Key。请在 ~/.aibrain/config/mem0.json 中配置 api_key 字段"
            f"，或设置环境变量 {_PROVIDER_DEFAULTS.get(provider, {}).get('env_key', '')}"
        )

    # 构建 LLM config（只包含 mem0 支持的字段）
    llm_model = cfg.get("llm_model") or _PROVIDER_DEFAULTS.get(provider, {}).get("model")
    llm_config = {
        "model": llm_model,
        "api_key": api_key,
    }
    # base_url 用于第三方代理
    if cfg.get("base_url"):
        if provider == "openai":
            os.environ["OPENAI_BASE_URL"] = cfg["base_url"]
        elif provider == "anthropic":
            os.environ["ANTHROPIC_BASE_URL"] = cfg["base_url"]
        elif provider == "minimax":
            os.environ["MINIMAX_API_BASE"] = cfg["base_url"]
        else:
            llm_config.setdefault("extra_body", {})

    # 修复 mem0 Anthropic LLM 的 ThinkingBlock 兼容性问题
    # MiniMax-M2.7 等模型返回 thinking block，mem0 假设第一个 block 是 TextBlock
    _patch_anthropic_thinking()

    config = {
        "llm": {
            "provider": provider,
            "config": llm_config,
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": _LOCAL_MODEL_PATH,
                "embedding_dims": brain_settings.embedding_dim,
            }
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": brain_settings.qdrant_host,
                "port": brain_settings.qdrant_port,
                "collection_name": cfg.get("collection_name", "mem0_memories"),
                "embedding_model_dims": brain_settings.embedding_dim,
            }
        },
    }

    client = Memory.from_config(config)
    logger.info(f"mem0 client initialized (provider={provider}, model={llm_model}, "
                f"collection={config['vector_store']['config']['collection_name']})")
    return client


def _patch_anthropic_thinking():
    """Monkey-patch mem0 的 AnthropicLLM 以兼容 ThinkingBlock（MiniMax-M2.7 等）

    问题：mem0 假设 response.content[0] 是 TextBlock，
    但 MiniMax-M2.7 等模型返回的第一个 block 是 ThinkingBlock。
    """
    try:
        import mem0.llms.anthropic as anthropic_module

        def _safe_generate_response(self, messages, **kwargs):
            system_prompt = ""
            user_messages = []
            for message in messages:
                if isinstance(message, dict):
                    role = message.get("role", "")
                    content = message.get("content", "")
                    if role == "system":
                        system_prompt = content
                    else:
                        user_messages.append({"role": role, "content": content})

            params = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "messages": [
                    *([{"role": "system", "content": system_prompt}] if system_prompt else []),
                    *user_messages,
                ],
            }

            response = self.client.messages.create(**params)
            # 安全提取：跳过 ThinkingBlock，找第一个 TextBlock
            for block in response.content:
                if hasattr(block, 'text') and isinstance(block.text, str) and getattr(block, 'type', '') == "text":
                    return block.text
            # 兜底
            texts = [b.text for b in response.content if hasattr(b, 'text') and isinstance(b.text, str)]
            return "\n".join(texts) if texts else str(response.content)

        anthropic_module.AnthropicLLM.generate_response = _safe_generate_response
        logger.info("Applied Anthropic ThinkingBlock compatibility patch")
    except Exception as e:
        logger.warning(f"Failed to apply Anthropic patch (non-fatal): {e}")
