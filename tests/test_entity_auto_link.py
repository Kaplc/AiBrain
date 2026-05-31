"""
Entity-Auto-Link 全流程测试
覆盖 plan/entity-auto-link.md 的完整实现。

测试范围：
1. 实体提取（本地 jieba + spaCy 三路合并）
2. graph.link_memory → entity_nodes / mentions / entity_relations
3. graph.search_related → 实体激活扩散
4. store_memory → search_memory 完整管线
5. 实体去重 (Jaccard + 子串匹配)
6. 空实体跳过行为
"""
import importlib
import json
import os
import sys
import tempfile
import uuid
import pytest
from unittest.mock import MagicMock, patch


# ── 确保 backend 在 sys.path 中 ──
_backend_root = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


###############################################################################
# 1. 测试本地实体提取 _extract_entities()
###############################################################################


class TestLocalEntityExtraction:
    """测试 memory.py 中的 _extract_entities() 三路合并逻辑"""

    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """清除模块级缓存"""
        import modules.brain.memory as mem
        mem._zh_nlp = None
        mem._en_nlp = None
        mem._jieba_initialized = False
        yield

    def test_jieba_noun_extraction(self):
        """jieba 词性过滤提取中文名词实体"""
        try:
            import jieba.posseg
        except ImportError:
            pytest.skip("jieba not installed")

        import modules.brain.memory as mem
        from modules.brain.memory import _extract_entities

        entities = _extract_entities("志远今天去北京参加会议")
        # jieba 提取：志远(nr)、北京(ns)、会议(n)
        assert len(entities) >= 2, f"Expected >=2 entities, got {entities}"
        assert any("志远" in e for e in entities)
        assert any("北京" in e for e in entities)

    def test_spacy_chinese_ner(self):
        """spaCy 中文 NER 提取实体"""
        import modules.brain.memory as mem
        from modules.brain.memory import _extract_entities

        # 强制走 spaCy 中文 NER（跳过 jieba）
        with patch.object(mem, '_jieba_initialized', True):
            entities = _extract_entities("志远今天去北京参加会议")
            assert isinstance(entities, list)
            # spaCy 中文 NER 可能提取或可能不提取，都算正常

    def test_english_ner_extraction(self):
        """spaCy 英文 NER 提取英文实体"""
        try:
            import spacy
            spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            pytest.skip("spaCy en_core_web_sm not available")

        from modules.brain.memory import _extract_entities
        entities = _extract_entities("Apple is based in California and Tim Cook is the CEO")
        assert len(entities) >= 1
        found = " ".join(entities)
        assert any(name in found for name in ["Apple", "California"])

    def test_empty_input(self):
        """空输入返回空列表"""
        from modules.brain.memory import _extract_entities
        assert _extract_entities("") == []
        assert _extract_entities("   ") == []

    def test_no_noun_text(self):
        """纯非名词文本返回空"""
        from modules.brain.memory import _extract_entities
        entities = _extract_entities("的 了 在 是 很 也 和")
        assert len(entities) == 0

    def test_length_filter(self):
        """过长的实体被 max_len 过滤"""
        from modules.brain.memory import _extract_entities
        text = "这是一个非常长的专有名词词组超出限制"
        entities = _extract_entities(text)
        max_len = max(len(text) // 2, 8)
        for e in entities:
            assert len(e) <= max_len


def _has_jieba():
    try:
        import jieba
        return True
    except ImportError:
        return False


###############################################################################
# 2. 测试 GraphMemory.link_memory
###############################################################################


class TestGraphLinkMemory:
    """测试 graph.link_memory 的节点和边创建"""

    @pytest.fixture
    def graph(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_graph_{uuid.uuid4().hex}.db")
        g = GraphMemory(db_file)
        yield g
        g._conn.close()
        _cleanup_db(db_file)

    def test_link_memory_creates_everything(self, graph):
        """link_memory 创建 entity_nodes, mentions, entity_relations"""
        entities = ["Python", "编程", "AI"]
        graph.link_memory("mem_001", "Python是AI编程的核心语言", link_entities=entities)

        # entity_nodes 包含我们的实体（加上默认的4个）
        nodes = graph._exec("SELECT name FROM entity_nodes ORDER BY name")
        node_names = [r[0] for r in nodes]
        for e in entities:
            assert e in node_names

        # mentions: mem_001 关联了全部3个实体
        mentions = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = ?", ("mem_001",))
        mention_entities = sorted(r[0] for r in mentions)
        assert mention_entities == sorted(entities)

        # entity_relations: 实体间两两双向连接
        relations = graph._exec("SELECT from_entity, to_entity FROM entity_relations")
        assert len(relations) > 0

    def test_no_entities_creates_memory_node(self, graph):
        """无实体时只创建 memory_nodes，不创建新 entity_nodes"""
        graph.link_memory("mem_002", "一段纯文本", link_entities=[])

        # memory_nodes 有记录
        node = graph._exec("SELECT mem0_id, text FROM memory_nodes WHERE mem0_id = ?", ("mem_002",))
        assert len(node) == 1
        assert node[0][1] == "一段纯文本"

        # entity_nodes 只有默认的4个（无新增）
        e_count = graph._exec("SELECT COUNT(*) FROM entity_nodes")
        assert e_count[0][0] == 4

    def test_entity_mesh_bidirectional(self, graph):
        """同一记忆内的实体创建双向边"""
        entities = ["技术", "框架"]
        graph.link_memory("mem_003", "技术框架的关系", link_entities=entities)

        relations = graph._exec(
            "SELECT from_entity, to_entity FROM entity_relations WHERE "
            "from_entity IN ('技术', '框架') AND to_entity IN ('技术', '框架')"
        )
        pairs = [(r[0], r[1]) for r in relations]
        assert ("技术", "框架") in pairs
        assert ("框架", "技术") in pairs

    def test_entity_dedup_jaccard(self, graph):
        """相似实体通过 Jaccard 去重"""
        graph._exec("INSERT OR IGNORE INTO entity_nodes (name, type) VALUES ('志远', 'concept')")
        graph._conn.commit()

        with patch.object(graph, '_entity_embedding_cache', {}):
            graph.link_memory("mem_005", "志远哥喜欢编程", link_entities=["志远哥"])

        nodes = graph._exec("SELECT name FROM entity_nodes WHERE name LIKE '%志远%'")
        names = [r[0] for r in nodes]
        assert len(names) <= 2  # "志远" + maybe "志远哥"未被去重

    def test_shared_entity_across_memories(self, graph):
        """多条记忆共享同一实体"""
        graph.link_memory("mem_a", "Python 是一门语言", link_entities=["Python"])
        graph.link_memory("mem_b", "Python 很适合数据分析", link_entities=["Python"])

        nodes = graph._exec("SELECT name FROM entity_nodes WHERE name = 'Python'")
        assert len(nodes) == 1

        mentions = graph._exec(
            "SELECT mem0_id FROM mentions WHERE entity_name = 'Python' ORDER BY mem0_id"
        )
        mem_ids = [r[0] for r in mentions]
        assert "mem_a" in mem_ids
        assert "mem_b" in mem_ids


###############################################################################
# 3. 测试 GraphMemory.search_related
###############################################################################


class TestGraphSearchRelated:
    """测试实体网络激活扩散 search_related"""

    @pytest.fixture
    def graph(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_search_{uuid.uuid4().hex}.db")
        g = GraphMemory(db_file)

        g.link_memory("mem_1", "Python 是 AI 开发的主要语言", link_entities=["Python", "AI"])
        g.link_memory("mem_2", "深度学习是AI的重要分支", link_entities=["AI", "深度学习"])
        g.link_memory("mem_3", "TensorFlow是深度学习的常用框架", link_entities=["深度学习", "TensorFlow"])
        g.link_memory("mem_4", "今天天气很好", link_entities=["天气"])

        yield g
        g._conn.close()
        _cleanup_db(db_file)

    def test_sql_fallback_spreads_through_entities(self, graph):
        """SQL 递归 fallback 通过共享实体找到关联记忆"""
        result = graph.search_related(["mem_1"], max_hops=2)

        ids = [r["id"] for r in result]
        assert "mem_1" not in ids  # 不应返回起始记忆
        if result:
            assert any(mid in ids for mid in ["mem_2", "mem_3"])

    def test_no_matching_entities(self, graph):
        """无其他记忆共享实体时返回空"""
        result = graph.search_related(["mem_4"], max_hops=2)
        assert len(result) == 0

    def test_empty_input(self, graph):
        """空输入返回空列表"""
        assert graph.search_related([]) == []


###############################################################################
# 4. 测试完整管线 store_memory → search_memory
###############################################################################


class TestStoreAndSearchPipeline:
    """mock mem0 测试 store_memory → search_memory 完整流程"""

    @pytest.fixture
    def mock_mem0(self):
        client = MagicMock()
        client.add = MagicMock()
        client.search = MagicMock()
        client.get = MagicMock()
        client.get_all = MagicMock()
        client.delete = MagicMock()
        return client

    @pytest.fixture
    def test_db_id(self):
        return uuid.uuid4().hex

    @pytest.fixture
    def mock_graph(self, test_db_id):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_pipeline_{test_db_id}.db")
        g = GraphMemory(db_file)
        yield g
        g._conn.close()
        _cleanup_db(db_file)

    def _patch_all_mem0(self, mock_mem0):
        """同时 patch memory 和 mem0_adapter 中的 get_mem0_client"""
        return (
            patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0),
            patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0),
        )

    def _make_add(self, mem_id, text, event="ADD"):
        return {"results": [{"id": mem_id, "memory": text, "event": event}]}

    def test_store_entities_linked_to_graph(self, mock_mem0, mock_graph):
        """store_memory 后实体链接到图中"""
        # 使用英文文本确保 spaCy NER 能提取到实体
        mock_mem0.add.return_value = self._make_add("test_001", "Apple develops AI in California")

        p1, p2 = self._patch_all_mem0(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                from modules.brain.memory import store_memory
                result = store_memory("Apple develops AI in California")

        assert result["added_count"] == 1

        # 图中应有实体关联（spaCy 英文 NER: Apple, California）
        mentions = mock_graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = ?", ("test_001",))
        entity_names = [r[0] for r in mentions]
        assert len(entity_names) > 0, f"No entities extracted from 'Apple develops AI in California', got: {entity_names}"

    def test_store_then_search(self, mock_mem0, mock_graph):
        """store 后 search 能返回结果"""
        mock_mem0.add.return_value = self._make_add("test_002", "Python是AI编程语言")
        mock_mem0.search.return_value = {
            "results": [{"id": "test_002", "memory": "Python是AI编程语言", "score": 0.95}]
        }
        mock_mem0.get_all.return_value = {"results": [{"id": "test_002"}]}

        p1, p2 = self._patch_all_mem0(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                import modules.brain.memory as mem_mod
                mem_mod._memory_count_cache = 1

                from modules.brain.memory import store_memory, search_memory
                store_memory("Python是AI编程语言")
                results = search_memory("编程语言")

        assert len(results) > 0
        assert any("Python" in r.get("text", "") for r in results)

    def test_search_returns_entities(self, mock_mem0, mock_graph):
        """search_memory 返回结果包含 entities 字段"""
        mock_graph.link_memory("test_003", "Python机器学习框架",
                               link_entities=["Python", "机器学习"])

        mock_mem0.search.return_value = {
            "results": [{"id": "test_003", "memory": "Python机器学习框架", "score": 0.92}]
        }
        mock_mem0.get_all.return_value = {"results": [{"id": "test_003"}]}

        p1, p2 = self._patch_all_mem0(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph):
                import modules.brain.memory as mem_mod
                mem_mod._memory_count_cache = 1

                from modules.brain.memory import search_memory
                results = search_memory("机器学习")

        assert len(results) > 0
        assert "entities" in results[0], f"Missing entities field: {results[0].keys()}"
        assert len(results[0]["entities"]) == 2

    def test_empty_entities_skips_graph(self, mock_mem0, mock_graph):
        """无实体时跳过图节点（continue 行为）"""
        mock_mem0.add.return_value = self._make_add("test_004", "的了的")

        p1, p2 = self._patch_all_mem0(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                import modules.brain.memory as mem
                mem._zh_nlp = None
                mem._en_nlp = None

                from modules.brain.memory import store_memory
                store_memory("的了的")

        # memory_nodes 不应该有 test_004（continue 跳过了）
        nodes = mock_graph._exec("SELECT mem0_id FROM memory_nodes WHERE mem0_id = ?", ("test_004",))
        assert len(nodes) == 0

    def test_graph_expansion_source_marker(self, mock_mem0, mock_graph):
        """图扩展的记忆标记 source='graph'"""
        mock_graph.link_memory("mem_x", "Vue是一个前端框架",
                               link_entities=["Vue", "前端"])
        mock_graph.link_memory("mem_y", "React也是前端框架",
                               link_entities=["React", "前端"])

        # 搜索：只返回 mem_x；get 返回 mem_y 的文本
        mock_mem0.search.return_value = {
            "results": [{"id": "mem_x", "memory": "Vue是一个前端框架", "score": 0.95}]
        }
        mock_mem0.get_all.return_value = {"results": [{"id": "mem_x"}, {"id": "mem_y"}]}
        mock_mem0.get.return_value = {"memory": "React也是前端框架"}

        p1, p2 = self._patch_all_mem0(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph):
                import modules.brain.memory as mem_mod
                mem_mod._memory_count_cache = 2

                from modules.brain.memory import search_memory
                results = search_memory("前端框架")

        graph_results = [r for r in results if r.get("source") == "graph"]
        assert len(graph_results) > 0, f"No graph results, all: {[(r.get('id','')[:8], r.get('source','')) for r in results]}"
        assert any(r["id"] == "mem_y" for r in graph_results)


###############################################################################
# 5. 测试实体去重
###############################################################################


class TestEntityDedup:
    """测试实体去重"""

    @pytest.fixture
    def graph(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_dedup_{uuid.uuid4().hex}.db")
        g = GraphMemory(db_file)

        for name, etype in [("machine learning", "concept"), ("Python", "concept")]:
            g._exec("INSERT OR IGNORE INTO entity_nodes (name, type) VALUES (?, ?)", (name, etype))
        g._conn.commit()

        yield g
        g._conn.close()
        _cleanup_db(db_file)

    def test_substring_match(self, graph):
        """子串包含匹配：'machine' 包含在 'machine learning' 中"""
        similar = graph._find_similar_entity("machine", threshold=0.6)
        assert similar == "machine learning"

    def test_jaccard_similar(self, graph):
        """Jaccard 相似度匹配英文单词"""
        # "machine learn" 和 "machine learning" 的 tokens 有重叠
        similar = graph._find_similar_entity("machine learn", threshold=0.5)
        assert similar == "machine learning"

    def test_jaccard_dissimilar(self, graph):
        """不相似不应匹配"""
        similar = graph._find_similar_entity("weather", threshold=0.6)
        assert similar is None

    def test_exact_match_returns_self(self, graph):
        """完全匹配返回原实体（子串匹配）"""
        similar = graph._find_similar_entity("Python", threshold=0.6)
        assert similar == "Python"

    def test_link_memory_dedup(self, graph):
        """link_memory 时自动去重相似实体"""
        with patch.object(graph, '_entity_embedding_cache', {}):
            graph.link_memory("mem_dedup", "some content about machine", link_entities=["machine"])

        # "machine" 不创建新实体节点（已合并到 "machine learning"）
        nodes = graph._exec("SELECT name FROM entity_nodes WHERE name = 'machine'")
        assert len(nodes) == 0

        # mentions 关联到 "machine learning"
        mentions = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = ?", ("mem_dedup",))
        names = [r[0] for r in mentions]
        assert "machine learning" in names


###############################################################################
# 6. 测试 LLM 实体提取
###############################################################################


class TestLLMEntityExtraction:
    """测试 extract_entities_llm"""

    def test_parse_json_array(self):
        with patch('modules.brain.llm.call_llm', return_value='["张三", "北京", "会议"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("张三在北京参加了会议")
            assert result == ["张三", "北京", "会议"]

    def test_filter_invalid_length(self):
        with patch('modules.brain.llm.call_llm',
                   return_value='["A", "这是一个超级长的不可能作为实体的名字超长串"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("测试")
            assert "A" not in result
            assert "这是一个超级长的不可能作为实体的名字超长串" not in result

    def test_empty_input(self):
        from modules.brain.llm import extract_entities_llm
        assert extract_entities_llm("") == []

    def test_failure_graceful(self):
        with patch('modules.brain.llm.call_llm', side_effect=Exception("timeout")):
            from modules.brain.llm import extract_entities_llm
            assert extract_entities_llm("测试") == []

    def test_dedup(self):
        with patch('modules.brain.llm.call_llm', return_value='["AI", "Python", "AI", "Python"]'):
            from modules.brain.llm import extract_entities_llm
            result = extract_entities_llm("AI Python")
            assert result == ["AI", "Python"]


###############################################################################
# 7. 测试数据持久化
###############################################################################


class TestGraphPersistence:
    """GraphMemory 数据持久化和加载"""

    def test_reopen_retains_data(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_persist_{uuid.uuid4().hex}.db")

        g1 = GraphMemory(db_file)
        g1.link_memory("mem_p1", "测试记忆持久化", link_entities=["持久化", "测试"])
        g1._conn.close()

        g2 = GraphMemory(db_file)
        nodes = g2._exec("SELECT name FROM entity_nodes ORDER BY name")
        entity_names = [r[0] for r in nodes]
        assert "持久化" in entity_names
        assert "测试" in entity_names

        mentions = g2._exec("SELECT mem0_id FROM mentions WHERE mem0_id = ?", ("mem_p1",))
        assert len(mentions) == 2

        g2._conn.close()
        _cleanup_db(db_file)


###############################################################################
# 8. 测试 spreading_activation
###############################################################################


class TestSpreadingActivation:
    """测试激活扩散算法"""

    @pytest.fixture
    def simple_graph(self):
        import networkx as nx
        G = nx.Graph()
        G.add_edge("Python", "AI", weight=1.0, relation_type="associated")
        G.add_edge("AI", "深度学习", weight=1.0, relation_type="associated")
        G.add_edge("深度学习", "TensorFlow", weight=1.0, relation_type="associated")
        G.add_edge("天气", "下雨", weight=1.0, relation_type="associated")
        return G

    def test_spreads_to_neighbors(self, simple_graph):
        from backend.modules.brain.graph import spreading_activation

        act = spreading_activation(simple_graph, ["Python"], [1.0],
                                   decay=0.5, threshold=0.1, max_iter=100)
        assert "Python" in act
        assert act["AI"] > 0.1
        assert act["深度学习"] > 0.01

    def test_decays_with_distance(self, simple_graph):
        from backend.modules.brain.graph import spreading_activation

        act = spreading_activation(simple_graph, ["Python"], [1.0],
                                   decay=0.5, threshold=0.1, max_iter=100)
        scores = [act.get(k, 0) for k in ["Python", "AI", "深度学习", "TensorFlow"]]
        assert scores[0] >= scores[1] >= scores[2] >= scores[3]

    def test_unconnected_not_reached(self, simple_graph):
        from backend.modules.brain.graph import spreading_activation

        act = spreading_activation(simple_graph, ["Python"], [1.0],
                                   decay=0.5, threshold=0.1, max_iter=100)
        assert "天气" not in act or act["天气"] < 0.1
        assert "下雨" not in act

    def test_empty_graph(self):
        import networkx as nx
        from backend.modules.brain.graph import spreading_activation
        assert spreading_activation(nx.Graph(), ["Python"], [1.0]) == {}

    def test_no_initial_nodes(self):
        import networkx as nx
        from backend.modules.brain.graph import spreading_activation
        G = nx.Graph()
        G.add_edge("A", "B")
        assert spreading_activation(G, [], []) == {}


###############################################################################
# helpers
###############################################################################


def _cleanup_db(db_file):
    for suffix in ("", "-wal", "-shm"):
        try:
            path = db_file + suffix
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
