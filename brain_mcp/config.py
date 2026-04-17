from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    collection_name: str = "memories"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    top_k: int = 10
    score_threshold: float = 0.5

    class Config:
        env_prefix = "QDRANT_"


settings = Settings()

# 多实例支持：从环境变量覆盖端口
import os
_http_port = os.environ.get('QDRANT_HTTP_PORT')
if _http_port:
    settings.qdrant_port = int(_http_port)
