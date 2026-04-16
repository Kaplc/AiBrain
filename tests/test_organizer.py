"""测试记忆整理模块"""
import pytest


class TestClassifyMemories:
    """测试 classify_memories 函数"""

    def test_classify_empty(self):
        """空列表应返回所有类型空列表"""
        from brain_mcp._organizer import classify_memories, TYPE_DESCRIPTIONS

        result = classify_memories([])
        assert result == {t: [] for t in TYPE_DESCRIPTIONS}

    def test_classify_single_memory(self):
        """单条记忆应该能正确分类"""
        from brain_mcp._organizer import classify_memories

        memories = [
            {"id": "1", "text": "我喜欢用 Python 编程", "timestamp": "2024-01-01"}
        ]
        result = classify_memories(memories)

        # 检查返回值结构
        assert "user" in result
        assert "feedback" in result
        assert "project" in result
        assert "reference" in result
        assert "ai" in result

        # 至少有一个类型有内容
        total = sum(len(v) for v in result.values())
        assert total == 1

    def test_classify_mixed_memories(self):
        """混合内容应该正确分类"""
        from brain_mcp._organizer import classify_memories

        memories = [
            {"id": "1", "text": "我喜欢吃火锅", "timestamp": "2024-01-01"},
            {"id": "2", "text": "这个功能有bug需要修复", "timestamp": "2024-01-02"},
            {"id": "3", "text": "项目需要重构代码结构", "timestamp": "2024-01-03"},
        ]
        result = classify_memories(memories)

        # 3条记忆应该被分类
        total = sum(len(v) for v in result.values())
        assert total == 3


class TestGenerateOrganizedText:
    """测试 generate_organized_text 函数"""

    def test_empty_categorized(self):
        """空分类应该生成空结构"""
        from brain_mcp._organizer import generate_organized_text, TYPE_DESCRIPTIONS

        categorized = {t: [] for t in TYPE_DESCRIPTIONS}
        result = generate_organized_text("测试", categorized)

        assert "# 记忆整理 - 主题: 测试" in result
        assert "## 整理时间:" in result

    def test_with_content(self):
        """有内容时应该生成完整结构"""
        from brain_mcp._organizer import generate_organized_text

        categorized = {
            "user": [{"id": "1", "text": "我喜欢 Python", "timestamp": "2024-01-01"}],
            "feedback": [],
            "project": [{"id": "2", "text": "项目代码", "timestamp": "2024-01-02"}],
            "reference": [],
            "ai": []
        }
        result = generate_organized_text("测试主题", categorized)

        assert "测试主题" in result
        assert "USER" in result
        assert "我喜欢 Python" in result
        assert "PROJECT" in result
        assert "项目代码" in result


class TestGenerateSummary:
    """测试 generate_summary 函数"""

    def test_empty_summary(self):
        """空分类应该返回空列表"""
        from brain_mcp._organizer import generate_summary, TYPE_DESCRIPTIONS

        categorized = {t: [] for t in TYPE_DESCRIPTIONS}
        result = generate_summary(categorized)
        assert result == []

    def test_with_summary(self):
        """有内容时应该生成摘要"""
        from brain_mcp._organizer import generate_summary

        categorized = {
            "user": [{"id": "1", "text": "我喜欢 Python 编程", "timestamp": "2024-01-01"}],
            "feedback": [],
            "project": [{"id": "2", "text": "项目代码需要重构", "timestamp": "2024-01-02"}],
            "reference": [],
            "ai": []
        }
        result = generate_summary(categorized)

        assert len(result) == 2
        assert result[0]["category"] == "user"
        assert result[0]["count"] == 1
        assert result[1]["category"] == "project"
        assert result[1]["count"] == 1


class TestOrganizeMemories:
    """测试 organize_memories 函数"""

    def test_empty_memories(self):
        """空记忆列表"""
        from brain_mcp._organizer import organize_memories

        result = organize_memories("测试", [])

        assert result["query"] == "测试"
        assert result["total_found"] == 0
        assert result["deleted_ids"] == []
        assert result["new_memory_id"] is None

    def test_result_structure(self):
        """结果结构完整性"""
        from brain_mcp._organizer import organize_memories

        memories = [
            {"id": "1", "text": "我喜欢 Python", "timestamp": "2024-01-01"},
            {"id": "2", "text": "项目需要重构", "timestamp": "2024-01-02"},
        ]
        result = organize_memories("测试", memories)

        # 检查必要字段
        assert "query" in result
        assert "total_found" in result
        assert "categories" in result
        assert "organized" in result
        assert "deleted_ids" in result
        assert "organized_text" in result

        # 应该删除了原始记忆
        assert result["deleted_ids"] == ["1", "2"]
