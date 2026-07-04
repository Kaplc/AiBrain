"""self_learn 搜索与提炼（digest.py）单元测试

覆盖：
  - 完整流程：web_search → 提取 URL → web_fetch → 截断
  - 每一步失败的降级路径
  - URL 提取过滤逻辑（.ico / duckduckgo）
  - 空 topic 边界
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ── 完整成功路径 ────────────────────────────────────────


class TestFullPipeline:

    def test_full_success(self):
        """web_search → 提取 URL → web_fetch → 返回截断摘要"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = [
            '搜索结果：https://example.com/article 这里有内容',
            '这是一篇关于如何学习 Python 异步编程的详细教程。'
            '它涵盖了 asyncio、协程、事件循环等核心概念。'
            '本文适合有一定 Python 基础的开发者阅读。' * 50,
        ]

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("Python异步编程", max_chars=5000)

        # 返回截断结果（<800 chars 不截断，>800 截断 + ...）
        assert result.endswith("...")
        assert len(result) <= 800 + 3  # 800 + "..."
        assert "asyncio" in result

    def test_short_content_no_truncation(self):
        """内容少于 800 字符时不截断"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = [
            'https://example.com/short',
            '这是一篇简短的内容。',
        ]

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("简短话题")

        assert result == "这是一篇简短的内容。"
        assert not result.endswith("...")

    def test_cleans_whitespace(self):
        """多余空白被压缩为单空格"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = [
            'https://example.com/doc',
            '多   余    空    白',
        ]

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("空白测试")

        assert result == "多 余 空 白"


# ── 降级路径 ────────────────────────────────────────────


class TestFallback:

    def test_tool_adapter_unavailable(self):
        """get_tool_adapter 抛异常 → 降级摘要"""
        with patch("main_brain.adapters.tools.get_tool_adapter", side_effect=ImportError("模拟异常")):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result
        assert "测试话题" in result

    def test_web_search_fails(self):
        """web_search 抛异常 → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = RuntimeError("网络错误")

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于「测试话题」" in result

    def test_web_search_returns_empty(self):
        """web_search 返空 → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.return_value = ""

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result

    def test_web_search_returns_error_prefix(self):
        """web_search 返 '错误' 开头 → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.return_value = "错误：API 限制超出"

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result

    def test_web_search_returns_search_failed_prefix(self):
        """web_search 返 '搜索失败' 开头 → 降级摘要（新格式）"""
        mock_tools = MagicMock()
        mock_tools.call.return_value = "搜索失败: 网络错误"

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result

    def test_web_search_returns_not_found(self):
        """web_search 含 '未找到结果' → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.return_value = "未找到结果，请重新描述"

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result

    def test_no_url_in_search_result(self):
        """搜索结果中无 URL → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.return_value = "纯文字结果，没有链接"

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result

    def test_web_fetch_fails(self):
        """web_fetch 抛异常 → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = [
            '搜索结果：https://example.com/article',
            RuntimeError("抓取超时"),
        ]

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于「测试话题」" in result

    def test_web_fetch_returns_error(self):
        """web_fetch 返 '错误' 开头 → 降级摘要"""
        mock_tools = MagicMock()
        mock_tools.call.side_effect = [
            'https://example.com/article',
            '错误：页面无法访问',
        ]

        with patch("main_brain.adapters.tools.get_tool_adapter", return_value=mock_tools):
            from main_brain.self_learn.digest import search_and_digest
            result = search_and_digest("测试话题")

        assert "关于" in result


# ── URL 提取 ────────────────────────────────────────────


class TestExtractFirstUrl:

    def test_extract_simple_url(self):
        """从文本中提取第一个 http URL"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("参考 https://example.com/article 了解详情")
        assert url == "https://example.com/article"

    def test_ignores_ico_url(self):
        """过滤掉 .ico 文件 URL"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("图标 https://example.com/favicon.ico 正文 https://example.com/page")
        assert url == "https://example.com/page"

    def test_ignores_duckduckgo_url(self):
        """过滤掉 duckduckgo.com URL"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("https://duckduckgo.com/l/?uddg=https://example.com")
        assert url is None

    def test_extracts_https(self):
        """支持 https URL"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("请参考 https://docs.python.org/3/library/asyncio.html")
        assert url == "https://docs.python.org/3/library/asyncio.html"

    def test_no_url_returns_none(self):
        """无 URL 返回 None"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("纯文本内容，没有链接")
        assert url is None

    def test_empty_text_returns_none(self):
        """空文本返回 None"""
        from main_brain.self_learn.digest import _extract_first_url
        url = _extract_first_url("")
        assert url is None


# ── 边界 ────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_topic(self):
        """空 topic 直接返回空字符串"""
        from main_brain.self_learn.digest import search_and_digest
        result = search_and_digest("")
        assert result == ""

    def test_fallback_summary_format(self):
        """降级摘要格式固定"""
        from main_brain.self_learn.digest import _fallback_summary
        result = _fallback_summary("测试")
        assert result == "关于「测试」的学习记录"
