"""测试 server.py 中 MCP tool 注册与调用"""
import pytest
from unittest.mock import patch, MagicMock


class TestServerTools:
    """测试 MCP server 工具注册与转发"""

    def test_store_tool_delegates_to_store_memory(self):
        with patch("brain_mcp.server.store_memory", return_value="已记住: hello") as mock_fn:
            from brain_mcp.server import store
            result = store(text="hello")
            mock_fn.assert_called_once_with("hello")
            assert result == "已记住: hello"

    def test_search_tool_delegates_to_search_memory(self):
        fake_results = [{"text": "foo", "score": 0.9, "timestamp": "2024-01-01"}]
        with patch("brain_mcp.server.search_memory", return_value=fake_results) as mock_fn:
            from brain_mcp.server import search
            result = search(query="foo")
            mock_fn.assert_called_once_with("foo")
            assert result == fake_results

    def test_list_all_tool_delegates_to_list_memories(self):
        fake_list = [{"id": "1", "text": "bar", "timestamp": "2024-01-01"}]
        with patch("brain_mcp.server.list_memories", return_value=fake_list) as mock_fn:
            from brain_mcp.server import list_all
            result = list_all()
            mock_fn.assert_called_once()
            assert result == fake_list

    def test_delete_tool_delegates_to_delete_memory(self):
        with patch("brain_mcp.server.delete_memory", return_value="已删除记忆: abc") as mock_fn:
            from brain_mcp.server import delete
            result = delete(memory_id="abc")
            mock_fn.assert_called_once_with("abc")
            assert result == "已删除记忆: abc"

    def test_mcp_instance_exists(self):
        from brain_mcp.server import mcp
        assert mcp is not None

    def test_mcp_name(self):
        from brain_mcp.server import mcp
        assert mcp.name == "Qdrant Memory Server"
