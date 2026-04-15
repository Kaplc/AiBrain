"""测试 tools.py 中的 store/search/list/delete 业务逻辑（mock qdrant_client）"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_client():
    """每个测试前重置全局 _client，避免测试间污染"""
    import mcp_qdrant.tools as t
    t._client = None
    yield
    t._client = None


@pytest.fixture
def mock_client():
    """返回一个 mock QdrantClient，并注入到 tools 模块"""
    client = MagicMock()
    # 模拟 get_collections 返回空集合列表
    client.get_collections.return_value = MagicMock(collections=[])
    import mcp_qdrant.tools as t
    t._client = client
    return client


# ──────────────────────────────────────────────
# store_memory 测试
# ──────────────────────────────────────────────
class TestStoreMemory:

    def test_store_returns_confirmation(self, mock_client):
        """存储成功后返回确认消息"""
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import store_memory
            result = store_memory("今天天气很好")
        assert "今天天气很好" in result

    def test_store_calls_upsert(self, mock_client):
        """调用 client.upsert 存入 Qdrant"""
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import store_memory
            store_memory("测试记忆")
        mock_client.upsert.assert_called_once()

    def test_store_upsert_correct_collection(self, mock_client):
        """upsert 使用正确的 collection_name"""
        from mcp_qdrant.config import settings
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.0] * 384]):
            from mcp_qdrant.tools import store_memory
            store_memory("check collection")
        call_kwargs = mock_client.upsert.call_args
        assert call_kwargs.kwargs["collection_name"] == settings.collection_name

    def test_store_point_has_text_payload(self, mock_client):
        """存储的 PointStruct payload 包含 text 字段"""
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.0] * 384]):
            from mcp_qdrant.tools import store_memory
            store_memory("payload test")
        points = mock_client.upsert.call_args.kwargs["points"]
        assert len(points) == 1
        assert points[0].payload["text"] == "payload test"

    def test_store_point_has_timestamp(self, mock_client):
        """存储的 PointStruct payload 包含 timestamp 字段"""
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.0] * 384]):
            from mcp_qdrant.tools import store_memory
            store_memory("timestamp test")
        points = mock_client.upsert.call_args.kwargs["points"]
        assert "timestamp" in points[0].payload

    def test_store_point_id_is_uuid(self, mock_client):
        """存储的 PointStruct ID 是 UUID 字符串"""
        import uuid
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.0] * 384]):
            from mcp_qdrant.tools import store_memory
            store_memory("uuid test")
        point_id = mock_client.upsert.call_args.kwargs["points"][0].id
        uuid.UUID(point_id)  # 如果不是合法 UUID 会抛异常

    def test_store_empty_text(self, mock_client):
        """空字符串也能存储"""
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.0] * 384]):
            from mcp_qdrant.tools import store_memory
            result = store_memory("")
        assert isinstance(result, str)


# ──────────────────────────────────────────────
# search_memory 测试
# ──────────────────────────────────────────────
class TestSearchMemory:

    def _make_search_result(self, text, score, ts="2024-01-01T00:00:00"):
        point = MagicMock()
        point.payload = {"text": text, "timestamp": ts}
        point.score = score
        return point

    def test_search_returns_list(self, mock_client):
        mock_client.query_points.return_value = MagicMock(points=[])
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            result = search_memory("test query")
        assert isinstance(result, list)

    def test_search_returns_correct_fields(self, mock_client):
        fake_point = self._make_search_result("记忆内容", 0.95)
        mock_client.query_points.return_value = MagicMock(points=[fake_point])
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            result = search_memory("query")
        assert result[0]["text"] == "记忆内容"
        assert result[0]["score"] == 0.95
        assert "timestamp" in result[0]

    def test_search_score_rounded_to_4_decimals(self, mock_client):
        fake_point = self._make_search_result("test", 0.123456789)
        mock_client.query_points.return_value = MagicMock(points=[fake_point])
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            result = search_memory("query")
        assert result[0]["score"] == round(0.123456789, 4)

    def test_search_multiple_results(self, mock_client):
        points = [self._make_search_result(f"memory {i}", 0.9 - i * 0.1) for i in range(3)]
        mock_client.query_points.return_value = MagicMock(points=points)
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            result = search_memory("query")
        assert len(result) == 3

    def test_search_empty_result(self, mock_client):
        mock_client.query_points.return_value = MagicMock(points=[])
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            result = search_memory("nothing")
        assert result == []

    def test_search_calls_query_points(self, mock_client):
        mock_client.query_points.return_value = MagicMock(points=[])
        with patch("mcp_qdrant.tools.encode_texts", return_value=[[0.1] * 384]):
            from mcp_qdrant.tools import search_memory
            search_memory("call test")
        mock_client.query_points.assert_called_once()


# ──────────────────────────────────────────────
# list_memories 测试
# ──────────────────────────────────────────────
class TestListMemories:

    def _make_scroll_result(self, id_, text, ts="2024-01-01T00:00:00"):
        point = MagicMock()
        point.id = id_
        point.payload = {"text": text, "timestamp": ts}
        return point

    def test_list_returns_list(self, mock_client):
        mock_client.scroll.return_value = ([], None)
        from mcp_qdrant.tools import list_memories
        result = list_memories()
        assert isinstance(result, list)

    def test_list_returns_all_memories(self, mock_client):
        points = [self._make_scroll_result(str(i), f"memory {i}") for i in range(5)]
        mock_client.scroll.return_value = (points, None)
        from mcp_qdrant.tools import list_memories
        result = list_memories()
        assert len(result) == 5

    def test_list_memory_has_id_text_timestamp(self, mock_client):
        points = [self._make_scroll_result("abc-123", "hello")]
        mock_client.scroll.return_value = (points, None)
        from mcp_qdrant.tools import list_memories
        result = list_memories()
        assert result[0]["id"] == "abc-123"
        assert result[0]["text"] == "hello"
        assert "timestamp" in result[0]

    def test_list_empty(self, mock_client):
        mock_client.scroll.return_value = ([], None)
        from mcp_qdrant.tools import list_memories
        result = list_memories()
        assert result == []

    def test_list_calls_scroll_with_limit(self, mock_client):
        mock_client.scroll.return_value = ([], None)
        from mcp_qdrant.tools import list_memories
        list_memories()
        mock_client.scroll.assert_called_once()
        call_kwargs = mock_client.scroll.call_args
        assert call_kwargs.kwargs.get("limit", 0) > 0


# ──────────────────────────────────────────────
# delete_memory 测试
# ──────────────────────────────────────────────
class TestDeleteMemory:

    def test_delete_returns_confirmation(self, mock_client):
        from mcp_qdrant.tools import delete_memory
        result = delete_memory("some-uuid-id")
        assert "some-uuid-id" in result

    def test_delete_calls_client_delete(self, mock_client):
        from mcp_qdrant.tools import delete_memory
        delete_memory("test-id-001")
        mock_client.delete.assert_called_once()

    def test_delete_correct_collection(self, mock_client):
        from mcp_qdrant.config import settings
        from mcp_qdrant.tools import delete_memory
        delete_memory("test-id-002")
        call_kwargs = mock_client.delete.call_args
        assert call_kwargs.kwargs["collection_name"] == settings.collection_name

    def test_delete_passes_correct_id(self, mock_client):
        from mcp_qdrant.tools import delete_memory
        delete_memory("my-special-id")
        call_kwargs = mock_client.delete.call_args
        selector = call_kwargs.kwargs["points_selector"]
        assert "my-special-id" in selector.points


# ──────────────────────────────────────────────
# _ensure_collection 测试
# ──────────────────────────────────────────────
class TestEnsureCollection:

    def test_creates_collection_if_not_exists(self, mock_client):
        """集合不存在时自动创建"""
        mock_client.get_collections.return_value = MagicMock(collections=[])
        import mcp_qdrant.tools as t
        t._client = mock_client
        t._ensure_collection()
        mock_client.create_collection.assert_called_once()

    def test_skips_creation_if_exists(self, mock_client):
        """集合已存在时不创建"""
        from mcp_qdrant.config import settings
        existing = MagicMock()
        existing.name = settings.collection_name
        mock_client.get_collections.return_value = MagicMock(collections=[existing])
        import mcp_qdrant.tools as t
        t._client = mock_client
        t._ensure_collection()
        mock_client.create_collection.assert_not_called()
