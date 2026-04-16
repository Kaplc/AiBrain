"""测试 config.py 中的 Settings 配置类"""
import pytest
from brain_mcp.config import Settings


class TestSettingsDefaults:
    """测试默认配置值"""

    def test_default_qdrant_host(self):
        s = Settings()
        assert s.qdrant_host == "localhost"

    def test_default_qdrant_port(self):
        s = Settings()
        assert s.qdrant_port == 6333

    def test_default_collection_name(self):
        s = Settings()
        assert s.collection_name == "memories"

    def test_default_embedding_model(self):
        s = Settings()
        assert s.embedding_model == "BAAI/bge-m3"

    def test_default_embedding_dim(self):
        s = Settings()
        assert s.embedding_dim == 384

    def test_default_top_k(self):
        s = Settings()
        assert s.top_k == 5


class TestSettingsEnvOverride:
    """测试通过环境变量覆盖配置"""

    def test_override_host(self, monkeypatch):
        monkeypatch.setenv("QDRANT_QDRANT_HOST", "192.168.1.1")
        s = Settings()
        assert s.qdrant_host == "192.168.1.1"

    def test_override_port(self, monkeypatch):
        monkeypatch.setenv("QDRANT_QDRANT_PORT", "6400")
        s = Settings()
        assert s.qdrant_port == 6400

    def test_override_collection_name(self, monkeypatch):
        monkeypatch.setenv("QDRANT_COLLECTION_NAME", "test_collection")
        s = Settings()
        assert s.collection_name == "test_collection"

    def test_override_embedding_dim(self, monkeypatch):
        monkeypatch.setenv("QDRANT_EMBEDDING_DIM", "768")
        s = Settings()
        assert s.embedding_dim == 768

    def test_override_top_k(self, monkeypatch):
        monkeypatch.setenv("QDRANT_TOP_K", "10")
        s = Settings()
        assert s.top_k == 10

    def test_override_embedding_model(self, monkeypatch):
        monkeypatch.setenv("QDRANT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        s = Settings()
        assert s.embedding_model == "all-MiniLM-L6-v2"
