"""
Embedding 客户端 — 通过 HTTP 调用 embed_server 独立服务

加载失败时自动降级为 hash-based 伪嵌入，保证 MCP 工具不中断。
"""
import hashlib
import json
import logging
import os
import urllib.request
import urllib.error
import numpy as np

logger = logging.getLogger(__name__)

# embed_server 端口缓存
_EMBED_PORT = None


def _get_embed_port() -> int:
    """从 .port_config 读取 embed 服务端口（第5位，索引4）"""
    global _EMBED_PORT
    if _EMBED_PORT is not None:
        return _EMBED_PORT

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_path = os.path.join(project_root, '.port_config')
    try:
        with open(config_path, 'r') as f:
            parts = f.read().strip().split(',')
        if len(parts) >= 5:
            _EMBED_PORT = int(parts[4].strip())
        else:
            _EMBED_PORT = 19402
    except Exception:
        _EMBED_PORT = 19402
    return _EMBED_PORT


def _call_embed_server(texts: list[str]) -> list[list[float]] | None:
    """调用 embed_server 的 /encode 接口

    Returns:
        向量列表，失败返回 None
    """
    port = _get_embed_port()
    url = f'http://127.0.0.1:{port}/encode'
    body = json.dumps({"texts": texts}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result.get("vectors")
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        logger.warning(f"embed_server unavailable (port={port}): {e}")
        return None
    except Exception as e:
        logger.warning(f"embed_server call failed: {e}")
        return None


def get_model_name():
    """获取当前配置的模型名称（兼容旧接口，实际由 embed_server 加载）"""
    from .config import settings
    name = settings.embedding_model
    if os.path.isabs(name) and os.path.isdir(name):
        return name
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    short_name = name.split("/")[-1] if "/" in name else name
    local_path = os.path.join(project_root, "models", short_name)
    if os.path.isdir(local_path):
        return local_path
    return name


def get_embedding_dim():
    """获取嵌入维度"""
    from .config import settings
    return settings.embedding_dim


def encode_texts(texts: list[str]) -> list[list[float]]:
    """文本向量化，优先调 embed_server，失败降级为 hash

    当前实现：
      1. 尝试通过 HTTP 调用 embed_server 生成向量
      2. 服务不可用时降级为 hash-based 伪嵌入（无语义但格式正确）
    """
    # 尝试 embed_server
    vectors = _call_embed_server(texts)
    if vectors is not None:
        return vectors

    # 降级：hash-based 伪嵌入
    logger.info("embed_server unavailable, using hash-based fallback embeddings")
    return hash_embed(texts, dim=get_embedding_dim())


def hash_embed(texts: list[str], dim: int = 1024) -> list[list[float]]:
    """Create deterministic pseudo-embeddings from text hash.

    This is a fallback for demo purposes when no model is available.
    It produces consistent embeddings but without semantic meaning.
    """
    embeddings = []
    for text in texts:
        features = []
        for n in [2, 3, 4]:  # character n-grams
            for i in range(len(text) - n + 1):
                ngram = text[i:i+n]
                h = int(hashlib.md5(ngram.encode()).hexdigest()[:8], 16)
                features.append(h % 1000)

        while len(features) < dim:
            h = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            features.extend([(h >> (i * 8)) & 0xFF for i in range(min(8, dim - len(features)))])

        vec = np.array(features[:dim], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        embeddings.append(vec.tolist())

    return embeddings
