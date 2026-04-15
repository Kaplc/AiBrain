"""测试 embedding.py 中的嵌入功能"""
import pytest
import numpy as np


# ──────────────────────────────────────────────
# hash_embed 测试
# ──────────────────────────────────────────────
class TestHashEmbed:
    """测试 hash_embed 回退嵌入函数"""

    def test_returns_correct_length(self):
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed(["hello world"], dim=384)
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_custom_dim(self):
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed(["test"], dim=128)
        assert len(result[0]) == 128

    def test_multiple_texts(self):
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed(["hello", "world", "foo"], dim=64)
        assert len(result) == 3
        for vec in result:
            assert len(vec) == 64

    def test_normalized(self):
        """输出向量应已归一化（L2 norm ≈ 1）"""
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed(["normalize me"], dim=128)
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 1e-5

    def test_deterministic(self):
        """相同输入产生相同输出"""
        from mcp_qdrant.embedding import hash_embed
        r1 = hash_embed(["deterministic test"], dim=64)
        r2 = hash_embed(["deterministic test"], dim=64)
        assert r1 == r2

    def test_different_texts_different_embeddings(self):
        """不同文本产生不同嵌入"""
        from mcp_qdrant.embedding import hash_embed
        r1 = hash_embed(["apple"], dim=64)
        r2 = hash_embed(["banana"], dim=64)
        assert r1 != r2

    def test_empty_string(self):
        """空字符串不报错"""
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed([""], dim=64)
        assert len(result) == 1
        assert len(result[0]) == 64

    def test_empty_list(self):
        """空列表返回空列表"""
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed([], dim=64)
        assert result == []

    def test_returns_float_list(self):
        """返回值为浮点数列表"""
        from mcp_qdrant.embedding import hash_embed
        result = hash_embed(["test"], dim=16)
        assert all(isinstance(v, float) for v in result[0])


# ──────────────────────────────────────────────
# encode_texts 测试（mock 模型）
# ──────────────────────────────────────────────
class TestEncodeTexts:
    """测试 encode_texts 函数"""

    def setup_method(self):
        import mcp_qdrant.embedding as emb
        emb._model = None

    def test_encode_uses_cached_model(self):
        """如果 _model 已加载，直接使用缓存"""
        import mcp_qdrant.embedding as emb

        class FakeModel:
            def encode(self, texts, normalize_embeddings=True):
                return np.ones((len(texts), 384), dtype=np.float32)

        emb._model = FakeModel()
        from mcp_qdrant.embedding import encode_texts
        result = encode_texts(["test"])
        assert result == [[1.0] * 384]

    def test_encode_fallback_on_model_error(self):
        """模型 encode 抛异常时走 hash 回退"""
        import mcp_qdrant.embedding as emb

        class BrokenModel:
            def encode(self, texts, normalize_embeddings=True):
                raise RuntimeError("encode error")

        emb._model = BrokenModel()
        from mcp_qdrant.embedding import encode_texts
        result = encode_texts(["fallback test"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_encode_offline_uses_hash(self, monkeypatch):
        """HF_HUB_OFFLINE=1 时走 hash 回退"""
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        import mcp_qdrant.embedding as emb
        emb._model = None
        from mcp_qdrant.embedding import encode_texts
        result = encode_texts(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_encode_multiple_texts(self):
        """多文本 mock 编码"""
        import mcp_qdrant.embedding as emb

        class FakeModel:
            def encode(self, texts, normalize_embeddings=True):
                return np.zeros((len(texts), 384), dtype=np.float32)

        emb._model = FakeModel()
        from mcp_qdrant.embedding import encode_texts
        result = encode_texts(["a", "b", "c"])
        assert len(result) == 3


# ──────────────────────────────────────────────
# 真实 bge-m3 模型测试
# ──────────────────────────────────────────────
BGE_M3_PATH = "./models/bge-m3"


@pytest.fixture(scope="module")
def bge_model():
    """加载真实 bge-m3 模型（module 级别，只加载一次）"""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(BGE_M3_PATH)
    return model


class TestBgeM3RealModel:
    """使用真实 bge-m3 模型的集成测试"""

    def test_encode_single_text(self, bge_model):
        vecs = bge_model.encode(["hello world"], normalize_embeddings=True)
        assert vecs.shape == (1, 1024)  # bge-m3 输出 1024 维

    def test_encode_multiple_texts(self, bge_model):
        texts = ["苹果", "香蕉", "橙子"]
        vecs = bge_model.encode(texts, normalize_embeddings=True)
        assert vecs.shape == (3, 1024)

    def test_output_normalized(self, bge_model):
        """输出向量应已归一化"""
        vecs = bge_model.encode(["normalize test"], normalize_embeddings=True)
        norm = np.linalg.norm(vecs[0])
        assert abs(norm - 1.0) < 1e-4

    def test_similar_texts_higher_score(self, bge_model):
        """语义相近的文本相似度 > 不相关文本"""
        vecs = bge_model.encode(
            ["猫是一种动物", "狗是一种动物", "今天天气很好"],
            normalize_embeddings=True
        )
        sim_related = float(np.dot(vecs[0], vecs[1]))
        sim_unrelated = float(np.dot(vecs[0], vecs[2]))
        assert sim_related > sim_unrelated

    def test_identical_texts_score_is_one(self, bge_model):
        """完全相同文本余弦相似度应接近 1"""
        vecs = bge_model.encode(["test sentence"] * 2, normalize_embeddings=True)
        sim = float(np.dot(vecs[0], vecs[1]))
        assert sim > 0.999

    def test_encode_chinese(self, bge_model):
        """中文文本正常编码"""
        vecs = bge_model.encode(["你好，世界！"], normalize_embeddings=True)
        assert vecs.shape == (1, 1024)

    def test_encode_long_text(self, bge_model):
        """长文本不报错"""
        long_text = "这是一段很长的文本。" * 100
        vecs = bge_model.encode([long_text], normalize_embeddings=True)
        assert vecs.shape[0] == 1

    def test_encode_via_encode_texts_with_real_model(self, bge_model):
        """通过 encode_texts 使用真实模型（注入到全局 _model）"""
        import mcp_qdrant.embedding as emb
        emb._model = bge_model
        from mcp_qdrant.embedding import encode_texts
        result = encode_texts(["real model test"])
        assert len(result) == 1
        assert len(result[0]) == 1024


# ──────────────────────────────────────────────
# get_model_name / get_embedding_dim 测试
# ──────────────────────────────────────────────
class TestHelpers:
    def test_get_model_name_default(self):
        from mcp_qdrant.embedding import get_model_name
        assert get_model_name() == "BAAI/bge-m3"

    def test_get_embedding_dim_default(self):
        from mcp_qdrant.embedding import get_embedding_dim
        assert get_embedding_dim() == 384
