from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    grpc_port: int = 6334
    collection_name: str = "memories"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    top_k: int = 10
    score_threshold: float = 0.5
    decay_lambda: float = 0.03
    search_limit_multiplier: int = 3
    forget_days: int = 100

    class Config:
        env_prefix = "QDRANT_"


settings = Settings()

# 多实例支持：从环境变量或 .port_config 覆盖端口
import os
_http_port = os.environ.get('QDRANT_HTTP_PORT')
_grpc_port = os.environ.get('QDRANT_GRPC_PORT')
if not _http_port:
    # 从 .port_config 文件读取（start.bat 自动生成）
    _port_config = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.port_config'))
    if os.path.exists(_port_config):
        try:
            with open(_port_config, 'r') as f:
                parts = f.read().strip().split(',')
                if len(parts) >= 3:
                    _http_port = parts[1]
                    _grpc_port = parts[2]
        except Exception:
            pass
if _http_port:
    settings.qdrant_port = int(_http_port)
if _grpc_port:
    settings.grpc_port = int(_grpc_port)
else:
    settings.grpc_port = settings.qdrant_port + 1
