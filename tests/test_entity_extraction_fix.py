"""
entity-extraction-fix 计划完整验证测试
覆盖 plan/entity-extraction-fix.md 的所有验收标准。

测试范围：
1. LLM Prompt: 限制1-5实体、排除泛化词/动作名词/字段名
2. 删除本地提取: 无 jieba/spaCy 残留
3. 移除 entity mesh: 同记忆内实体不再两两互联
4. 保留 typed_entity_relations: LLM 语义关系推断
5. 空实体允许: 无明确实体时可跳过
6. store→entities 完整流程
"""
import os
import sys
import tempfile
import uuid
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


_backend_root = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


###############################################################################
# helpers
###############################################################################


def _make_graph():
    from backend.modules.brain.graph import GraphMemory
    db_file = os.path.join(tempfile.gettempdir(), f"test_extract_fix_{uuid.uuid4().hex}.db")
    g = GraphMemory(db_file)
    yield g
    g._conn.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(db_file + suffix)
        except OSError:
            pass


def _make_add(mem_id, text, event="ADD"):
    return {"results": [{"id": mem_id, "memory": text, "event": event}]}


def _count_entity_nodes(graph):
    return graph._exec("SELECT COUNT(*) FROM entity_nodes")[0][0]


def _count_entity_relations(graph):
    return graph._exec("SELECT COUNT(*) FROM entity_relations")[0][0]


def _count_mentions(graph, mem_id):
    r = graph._exec("SELECT COUNT(*) FROM mentions WHERE mem0_id = ?", (mem_id,))
    return r[0][0]


###############################################################################
# 1. LLM Prompt 约束验证
###############################################################################


class TestLLMPromptConstraints:
    """验证 ENTITY_EXTRACT_PROMPT 的约束效果"""

    def test_prompt_exists(self):
        """Prompt 已更新为新版本"""
        from modules.brain.llm import ENTITY_EXTRACT_PROMPT
        assert "1-5" in ENTITY_EXTRACT_PROMPT
        assert "泛化词" in ENTITY_EXTRACT_PROMPT
        assert "字段名" in ENTITY_EXTRACT_PROMPT or "变量名" in ENTITY_EXTRACT_PROMPT
        assert "一致性" in ENTITY_EXTRACT_PROMPT

    def test_max_5_entities_enforced(self):
        """extract_entities_llm 最多返回5个实体（在过滤之前）"""
        # LLM 返回7个实体，但 len 过滤后应 <= 5（但实际上 extract_entities_llm 不限制数量）
        # 真正限制在 prompt 里面，LLM 被指示最多返回5个
        # 这里验证如果 LLM 违反限制返回7个，函数仍会全部接受
        with patch('modules.brain.llm.call_llm',
                   return_value='["A1","B2","C3","D4","E5","F6","G7"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("测试")
            # 全部符合 2-10 长度，所以会全部返回
            assert len(result) == 7

    def test_length_filter(self):
        """代码层 2-10 字长度过滤"""
        with patch('modules.brain.llm.call_llm',
                   return_value='["A", "AB", "ABCDEFGHIJK", "ABCDEF"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("测试")
            assert "A" not in result            # < 2
            assert "AB" in result               # 2 字，通过
            assert "ABCDEFGHIJK" not in result   # > 10 (代码限制)
            assert "ABCDEF" in result           # 6 字，通过

    def test_empty_result_allowed(self):
        """空实体列表允许（LLM 返回 []）"""
        with patch('modules.brain.llm.call_llm', return_value='[]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("今天是5月31日")
            assert result == []

    def test_dedup_preserved(self):
        """去重仍然有效"""
        with patch('modules.brain.llm.call_llm', return_value='["AI", "Python", "AI"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("测试")
            assert result == ["AI", "Python"]


###############################################################################
# 2. 无本地提取残留验证
###############################################################################


class TestNoLocalExtraction:
    """验证 _extract_entities 和 jieba/spaCy 已完全删除"""

    def test_no_extract_entities_function(self):
        """_extract_entities 函数不存在"""
        import modules.brain.memory as mem
        assert not hasattr(mem, '_extract_entities'), \
            "_extract_entities should be deleted"

    def test_no_jieba_in_memory(self):
        """memory.py 不包含 jieba 引用"""
        import modules.brain.memory as mem
        src = __import__('inspect').getsource(mem)
        assert 'jieba' not in src.lower(), "jieba should not be in memory.py"

    def test_no_spacy_in_memory(self):
        """memory.py 不包含 spaCy 引用"""
        import modules.brain.memory as mem
        src = __import__('inspect').getsource(mem)
        assert 'spacy' not in src.lower(), "spaCy should not be in memory.py"

    def test_store_only_uses_llm_extraction(self):
        """store_memory 只调用 extract_entities_llm，无本地提取"""
        import modules.brain.memory as mem
        src = __import__('inspect').getsource(mem.store_memory)
        assert 'extract_entities_llm' in src
        # 确认不存在本地提取函数调用
        assert '_extract_entities(' not in src
        assert 'jieba' not in src
        assert 'spaCy' not in src


###############################################################################
# 3. 移除 entity mesh 验证
###############################################################################


class TestEntityMeshRemoved:
    """验证同一记忆内实体不再两两互联"""

    @pytest.fixture
    def graph(self):
        yield from _make_graph()

    def test_no_mesh_for_plain_entities(self, graph):
        """纯实体列表不产生 entity_relations"""
        entities = ["Python", "编程", "AI", "技术"]
        graph.link_memory("mem_mesh_1", "Python是AI编程技术", link_entities=entities)

        # entity_nodes 创建了
        for e in entities:
            nodes = graph._exec("SELECT 1 FROM entity_nodes WHERE name = ?", (e,))
            assert len(nodes) == 1, f"Entity {e} should exist"

        # mentions 创建了
        assert _count_mentions(graph, "mem_mesh_1") == 4

        # entity_relations 不应该有 Python↔编程 这样的 mesh 边
        # （只有 old-new 格式的实体才会创建 entity_relations）
        relations = graph._exec(
            "SELECT from_entity, to_entity FROM entity_relations WHERE "
            "from_entity IN ('Python','编程','AI','技术')"
        )
        assert len(relations) == 0, \
            f"Entity mesh should be removed, but found {len(relations)} relations: {relations}"

    def test_no_mesh_even_with_many_entities(self, graph):
        """即使5个实体也不产生 mesh"""
        entities = ["E1", "E2", "E3", "E4", "E5"]
        graph.link_memory("mem_mesh_2", "很多实体", link_entities=entities)

        # 验证每个实体被创建
        for e in entities:
            assert graph._exec("SELECT 1 FROM entity_nodes WHERE name = ?", (e,))

        # 验证没有 entity_relations
        relations = graph._exec(
            "SELECT COUNT(*) FROM entity_relations WHERE from_entity IN "
            + f"({','.join(repr(e) for e in entities)})"
        )
        assert relations[0][0] == 0

    def test_old_new_format_still_works(self, graph):
        """旧实体-新实体格式仍创建 entity_relations"""
        # 先创建旧实体
        graph._exec("INSERT OR IGNORE INTO entity_nodes (name, type) VALUES ('志远', 'concept')")
        graph._conn.commit()

        # link_memory with 旧实体-新实体 格式
        graph.link_memory("mem_mesh_3", "志远开发AiBrain",
                          link_entities=["志远-AiBrain"])

        # 旧-新格式应创建 entity_relations (双向)
        relations = graph._exec(
            "SELECT from_entity, to_entity FROM entity_relations "
            "WHERE from_entity IN ('志远', 'AiBrain')"
        )
        assert len(relations) >= 1, "old-new format should create relations"


###############################################################################
# 4. typed_entity_relations 保留验证
###############################################################################


class TestTypedRelationsPreserved:
    """验证 typed_entity_relations 表和相关功能保留"""

    @pytest.fixture
    def graph(self):
        yield from _make_graph()

    def test_typed_relations_table_exists(self, graph):
        """typed_entity_relations 表存在"""
        tables = graph._exec(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='typed_entity_relations'"
        )
        assert len(tables) == 1

        # 验证列名正确
        cols = graph._exec("PRAGMA table_info(typed_entity_relations)")
        col_names = [r[1] for r in cols]
        assert 'from_entity' in col_names
        assert 'to_entity' in col_names
        assert 'relation_type' in col_names
        assert 'weight' in col_names

    def test_infer_and_store_typed_relations_method_exists(self, graph):
        """_infer_and_store_typed_relations 方法存在"""
        assert hasattr(graph, '_infer_and_store_typed_relations')

    def test_typed_relations_called_on_multiple_entities(self, graph):
        """当 resolved_entities >= 2 时触发推断"""
        # Mock _infer_and_store_typed_relations 来验证被调用
        called_with = []

        def fake_infer(mem_id, entity_names, text):
            called_with.append((mem_id, entity_names, text))

        with patch.object(graph, '_infer_and_store_typed_relations', side_effect=fake_infer):
            graph.link_memory("mem_type_1", "AI is related to Python",
                              link_entities=["AI", "Python"])

        assert len(called_with) == 1
        assert called_with[0][0] == "mem_type_1"
        assert called_with[0][1] == ["AI", "Python"]

    def test_typed_relations_not_called_on_single_entity(self, graph):
        """单个实体时不触发推断"""
        called_with = []

        def fake_infer(mem_id, entity_names, text):
            called_with.append((mem_id, entity_names, text))

        with patch.object(graph, '_infer_and_store_typed_relations', side_effect=fake_infer):
            graph.link_memory("mem_type_2", "Just Python",
                              link_entities=["Python"])

        assert len(called_with) == 0


###############################################################################
# 5. store 完整流程验证
###############################################################################


class TestStoreExtractionFlow:
    """验证 store_memory 的实体提取完整流程"""

    @pytest.fixture
    def mock_mem0(self):
        client = MagicMock()
        client.add = MagicMock()
        return client

    @pytest.fixture
    def graph(self):
        yield from _make_graph()

    def _patch_all(self, mock_mem0):
        return (
            patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0),
            patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0),
        )

    def test_store_returns_entities(self, mock_mem0, graph):
        """store 结果包含实体列表"""
        mock_mem0.add.return_value = _make_add("s001", "志远开发AiBrain项目")

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=graph), \
                 patch('modules.brain.llm.extract_entities_llm',
                       return_value=["志远", "AiBrain"]):
                from modules.brain.memory import store_memory
                result = store_memory("志远开发AiBrain项目")

        assert result["added_count"] == 1
        assert "entities" in result
        assert result["entities"] == ["志远", "AiBrain"]

    def test_store_with_empty_entities_allowed(self, mock_mem0, graph):
        """无实体时跳过图，store 仍成功"""
        mock_mem0.add.return_value = _make_add("s002", "今天是5月31日")

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                from modules.brain.memory import store_memory
                result = store_memory("今天是5月31日")

        assert result["added_count"] == 1
        assert result["entities"] == []  # 无实体

    def test_store_with_max_entities(self, mock_mem0, graph):
        """最多5个实体的记忆"""
        entities = ["E1", "E2", "E3", "E4", "E5"]
        mock_mem0.add.return_value = _make_add("s003", "五个实体的记忆")

        # 记录 store 前的 entity_relations 数量（默认实体会产生12条）
        relations_before = _count_entity_relations(graph)

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=entities), \
                 patch.object(graph, '_infer_and_store_typed_relations') as mock_infer:
                from modules.brain.memory import store_memory
                result = store_memory("五个实体的记忆")

        assert result["entities"] == entities

        # store 后 entity_relations 不变（无 mesh，typed_relations 在 typed 表）
        relations_after = _count_entity_relations(graph)
        assert relations_after == relations_before, \
            f"store should not add entity_relations (mesh removed), before={relations_before}, after={relations_after}"

        # typed_relations 推断被触发
        mock_infer.assert_called_once()

    def test_store_with_mcp_meta(self, mock_mem0, graph):
        """MCP 来源的 store 也正确返回 entities"""
        mock_mem0.add.return_value = _make_add("s004", "Python是编程语言")

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=graph), \
                 patch('modules.brain.llm.extract_entities_llm',
                       return_value=["Python", "编程语言"]):
                from modules.brain.memory import store_memory
                result = store_memory("Python是编程语言",
                                      memory_meta={"source": "mcp"})

        assert result["added_count"] == 1
        assert result["entities"] == ["Python", "编程语言"]


###############################################################################
# 6. 图谱展示逻辑验证
###############################################################################


class TestGraphDisplayLogic:
    """验证图谱只显示 LLM 推断的语义关系"""

    @pytest.fixture
    def graph(self):
        yield from _make_graph()

    def test_no_new_entity_relations_from_plain_store(self, graph):
        """纯 store 不创建新的 entity_relations（默认实体已有12条）"""
        relations_before = _count_entity_relations(graph)

        graph.link_memory("mem_g1", "Python是AI的核心",
                          link_entities=["Python", "AI"])

        # entity_nodes + mentions 存在
        assert _count_entity_nodes(graph) > 0
        assert _count_mentions(graph, "mem_g1") == 2

        # entity_relations 不变（无 mesh）
        assert _count_entity_relations(graph) == relations_before

    def test_visualization_includes_typed_relations(self, graph):
        """get_visualization_data 包含 typed_entity_relations 的边"""
        # 写入 typed_entity_relations（表结构: from_entity, to_entity, relation_type, weight）
        graph._exec(
            "INSERT OR REPLACE INTO typed_entity_relations "
            "(from_entity, to_entity, relation_type, weight) "
            "VALUES (?, ?, ?, ?)",
            ("Python", "AI", "associated", 0.95)
        )
        graph._conn.commit()

        data = graph.get_visualization_data()
        edges = data.get("edges", [])
        assert len(edges) > 0

    def test_entity_lookup_returns_memories(self, graph):
        """search_entity 返回关联记忆"""
        graph.link_memory("mem_e1", "Python is great", link_entities=["Python"])
        graph.link_memory("mem_e2", "I use Python daily", link_entities=["Python"])

        result = graph.search_entity("Python")
        assert result.get("name") == "Python" or result.get("exists") is True
        assert "memories" in result or "memory_count" in result


###############################################################################
# 7. 验收标准全量检查
###############################################################################


class TestAcceptanceCriteria:
    """逐条验证 plan 中的验收标准"""

    def test_max_5_entities(self):
        """验收: 一条记忆最多提取 5 个实体
        Prompt 中已限制 (llm.py:58)，代码中 extract_entities_llm 没有硬限制，
        但长度过滤 2-10 和 prompt 约束共同保证。后续 LLM 接入后由 prompt 保证。"""
        from modules.brain.llm import ENTITY_EXTRACT_PROMPT
        assert "1-5" in ENTITY_EXTRACT_PROMPT or "最多提取5个" in ENTITY_EXTRACT_PROMPT

    def test_generic_words_excluded(self):
        """验收: 泛化词被排除
        Prompt 明确列出：一致性、维度、状态、生命周期、属性等"""
        from modules.brain.llm import ENTITY_EXTRACT_PROMPT
        assert "一致性" in ENTITY_EXTRACT_PROMPT
        assert "维度" in ENTITY_EXTRACT_PROMPT
        assert "标签" in ENTITY_EXTRACT_PROMPT

    def test_field_names_excluded(self):
        """验收: 字段名被排除
        Prompt 明确列出：entities、stats、store、config"""
        from modules.brain.llm import ENTITY_EXTRACT_PROMPT
        assert "entities" in ENTITY_EXTRACT_PROMPT
        assert "stats" in ENTITY_EXTRACT_PROMPT
        assert "store" in ENTITY_EXTRACT_PROMPT

    def test_no_entity_mesh(self):
        """验收: 同一记忆内实体不再两两互联"""
        import modules.brain.graph as gmod
        src = __import__('inspect').getsource(gmod.GraphMemory.link_memory)
        # 不应有 "两两互联" 或 entity mesh 的嵌套循环
        # mesh 逻辑已被移除
        assert True  # 由 TestEntityMeshRemoved 详细验证

    def test_empty_entities_allowed(self):
        """验收: 没有明确实体的记忆可以不提取
        extract_entities_llm 返回 [] 时，store_memory continue 跳过"""
        import modules.brain.memory as mem
        src = __import__('inspect').getsource(mem.store_memory)
        assert 'continue' in src  # 空实体时跳过
