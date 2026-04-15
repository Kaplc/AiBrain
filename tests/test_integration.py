"""端到端集成测试：使用真实 bge-m3 + 内存版 Qdrant"""
import pytest
import numpy as np


BGE_M3_PATH = "./models/bge-m3"


@pytest.fixture(scope="module")
def qdrant_memory_client():
    """使用内存模式 QdrantClient（不需要运行 Qdrant 服务）"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="test_memories",
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
    )
    return client


@pytest.fixture(scope="module")
def bge_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(BGE_M3_PATH)


@pytest.fixture(scope="module")
def populated_client(qdrant_memory_client, bge_model):
    """预填充一些记忆数据"""
    from qdrant_client.models import PointStruct
    import uuid
    from datetime import datetime

    texts = [
        "Python 是一种编程语言",
        "今天下雨了，记得带伞",
        "明天有个重要会议",
        "我喜欢吃火锅",
        "深度学习需要大量数据",
    ]
    vectors = bge_model.encode(texts, normalize_embeddings=True)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vectors[i].tolist(),
            payload={"text": texts[i], "timestamp": datetime.now().isoformat()}
        )
        for i in range(len(texts))
    ]
    qdrant_memory_client.upsert(collection_name="test_memories", points=points)
    return qdrant_memory_client, texts


class TestE2EStoreAndSearch:
    """端到端：存储 + 检索"""

    def test_store_and_retrieve(self, populated_client, bge_model):
        """存入文本后能检索到"""
        client, texts = populated_client
        query = "编程语言"
        query_vec = bge_model.encode([query], normalize_embeddings=True)[0].tolist()
        results = client.query_points(
            collection_name="test_memories",
            query=query_vec,
            limit=3
        )
        top_texts = [r.payload["text"] for r in results.points]
        assert any("编程" in t or "Python" in t for t in top_texts)

    def test_semantic_search_ranks_relevant_higher(self, populated_client, bge_model):
        """语义检索：相关内容排名应高于不相关内容"""
        client, _ = populated_client
        query_vec = bge_model.encode(["机器学习算法"], normalize_embeddings=True)[0].tolist()
        results = client.query_points(
            collection_name="test_memories",
            query=query_vec,
            limit=5
        )
        top_text = results.points[0].payload["text"]
        # 深度学习 / Python 应排在前面
        assert "深度学习" in top_text or "Python" in top_text

    def test_search_returns_scores(self, populated_client, bge_model):
        """检索结果包含相似度分数"""
        client, _ = populated_client
        query_vec = bge_model.encode(["会议安排"], normalize_embeddings=True)[0].tolist()
        results = client.query_points(
            collection_name="test_memories",
            query=query_vec,
            limit=3
        )
        for r in results.points:
            assert 0.0 <= r.score <= 1.0

    def test_scroll_returns_all(self, populated_client):
        """scroll 能返回所有记录"""
        client, texts = populated_client
        results, _ = client.scroll(collection_name="test_memories", limit=100)
        assert len(results) == len(texts)

    def test_delete_removes_entry(self, qdrant_memory_client, bge_model):
        """删除后条目消失"""
        from qdrant_client.models import PointStruct, PointIdsList
        import uuid
        from datetime import datetime

        pid = str(uuid.uuid4())
        vec = bge_model.encode(["临时记忆"], normalize_embeddings=True)[0].tolist()
        qdrant_memory_client.upsert(
            collection_name="test_memories",
            points=[PointStruct(
                id=pid,
                vector=vec,
                payload={"text": "临时记忆", "timestamp": datetime.now().isoformat()}
            )]
        )
        # 确认存在
        before, _ = qdrant_memory_client.scroll(collection_name="test_memories", limit=100)
        before_ids = [str(p.id) for p in before]
        assert pid in before_ids

        # 删除
        qdrant_memory_client.delete(
            collection_name="test_memories",
            points_selector=PointIdsList(points=[pid])
        )

        # 确认不存在
        after, _ = qdrant_memory_client.scroll(collection_name="test_memories", limit=100)
        after_ids = [str(p.id) for p in after]
        assert pid not in after_ids

    def test_upsert_updates_existing(self, qdrant_memory_client, bge_model):
        """相同 ID upsert 会更新 payload"""
        from qdrant_client.models import PointStruct
        import uuid
        from datetime import datetime

        pid = str(uuid.uuid4())
        vec = bge_model.encode(["初始内容"], normalize_embeddings=True)[0].tolist()
        qdrant_memory_client.upsert(
            collection_name="test_memories",
            points=[PointStruct(id=pid, vector=vec, payload={"text": "初始内容", "timestamp": "t1"})]
        )
        vec2 = bge_model.encode(["更新内容"], normalize_embeddings=True)[0].tolist()
        qdrant_memory_client.upsert(
            collection_name="test_memories",
            points=[PointStruct(id=pid, vector=vec2, payload={"text": "更新内容", "timestamp": "t2"})]
        )
        results, _ = qdrant_memory_client.scroll(collection_name="test_memories", limit=100)
        target = next((p for p in results if str(p.id) == pid), None)
        assert target is not None
        assert target.payload["text"] == "更新内容"


class TestE2EFullPipeline:
    """端到端：通过 tools 模块的完整链路（mock Qdrant 连接，使用真实 embedding）"""

    @pytest.fixture(autouse=True)
    def setup_tools(self, bge_model):
        """注入真实模型 + 内存版 Qdrant client"""
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        import mcp_qdrant.tools as t
        import mcp_qdrant.embedding as emb

        emb._model = bge_model

        client = QdrantClient(":memory:")
        client.create_collection(
            collection_name="memories",
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
        )
        t._client = client
        yield
        t._client = None
        emb._model = None

    def test_store_and_search_pipeline(self):
        from mcp_qdrant.tools import store_memory, search_memory
        store_memory("Python 是一种编程语言")
        store_memory("今天天气很好")
        results = search_memory("编程")
        assert len(results) > 0
        assert any("Python" in r["text"] or "编程" in r["text"] for r in results)

    def test_store_list_delete_pipeline(self):
        from mcp_qdrant.tools import store_memory, list_memories, delete_memory
        store_memory("记忆A")
        store_memory("记忆B")

        memories = list_memories()
        assert len(memories) >= 2

        mem_id = memories[0]["id"]
        delete_memory(mem_id)

        after = list_memories()
        ids_after = [str(m["id"]) for m in after]
        assert str(mem_id) not in ids_after

    def test_search_top_k_limit(self):
        from mcp_qdrant.tools import store_memory, search_memory
        from mcp_qdrant.config import settings

        for i in range(10):
            store_memory(f"记忆条目 {i}")

        results = search_memory("记忆")
        assert len(results) <= settings.top_k
