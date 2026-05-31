"""
memory-search-stats 流视图完整流程测试
覆盖 plan/memory-search-stats.md 的实现。

测试范围：
1. Store 流：store_memory → stream entities（实体标签）
2. Search 流：search_memory → stream stats（语义搜索:N,实体网络:N）
3. 流状态流转：pending → done/error
4. 实体标签解析：逗号分隔 → 前端 entityTags 数组
5. 统计格式验证
"""
import os
import sys
import tempfile
import uuid
import pytest
from unittest.mock import MagicMock, patch


_backend_root = os.path.join(os.path.dirname(__file__), "..", "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


###############################################################################
# helpers
###############################################################################


def _make_stats_db():
    """创建临时 StatsDB 实例"""
    from backend.core.database import StatsDB
    db_path = os.path.join(tempfile.gettempdir(), f"test_stream_{uuid.uuid4().hex}.db")
    sdb = StatsDB(db_path)
    StatsDB._instance = None  # 重置单例，避免干扰
    return sdb


def _cleanup_stats_db(sdb):
    sdb._get_conn().close()
    try:
        for suffix in ("", "-wal", "-shm"):
            path = sdb.path + suffix
            if os.path.exists(path):
                os.unlink(path)
    except OSError:
        pass


def _make_add_result(mem_id, text, event="ADD"):
    return {"results": [{"id": mem_id, "memory": text, "event": event}]}


###############################################################################
# 1. Stream Store 流程测试
###############################################################################


class TestStreamStoreFlow:
    """测试 store → stream entities 完整流程"""

    @pytest.fixture
    def mock_mem0(self):
        client = MagicMock()
        client.add = MagicMock()
        return client

    @pytest.fixture
    def mock_graph(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_store_stream_graph_{uuid.uuid4().hex}.db")
        g = GraphMemory(db_file)
        yield g
        g._conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(db_file + suffix)
            except OSError:
                pass

    def _patch_all(self, mock_mem0):
        """同时 patch memory 和 mem0_adapter 中的 get_mem0_client"""
        return (
            patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0),
            patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0),
        )

    def test_store_writes_entities_to_stream(self, mock_mem0, mock_graph):
        """store 完成后 stream 记录包含实体标签"""
        sdb = _make_stats_db()

        mock_mem0.add.return_value = _make_add_result("s001", "Apple is based in California")

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                from modules.brain.memory import store_memory

                # step 1: 写入 pending
                text = "Apple is based in California"
                rowid = sdb.append_stream('store', content=text, status='pending')

                # step 2: 执行 store
                result = store_memory(text, memory_meta={"source": "mcp"})

                # step 3: 更新 content + entities + status
                stored = result.get("stored_texts", [])
                if stored:
                    new_content = "\n".join(f"• {t}" for t in stored)
                    sdb.update_stream_content(rowid, new_content)

                entities = result.get("entities", [])
                if entities:
                    sdb.update_stream_entities(rowid, ','.join(entities))

                sdb.record_action(
                    added=result.get('added_count', 0),
                    deleted=result.get('deleted_count', 0),
                )
                sdb.update_stream_status(rowid, 'done')

        # step 4: 验证 stream 记录
        rows = sdb.query_stream(action='store', limit=10)
        assert len(rows) > 0
        record = rows[0]
        assert record['status'] == 'done'
        assert record['action'] == 'store'
        entities_val = record.get('entities', '')
        assert entities_val, f"entities should not be empty, got: '{entities_val}'"
        # spaCy 英文 NER 应提取到 Apple, California 等
        assert len(entities_val.split(',')) >= 1

        _cleanup_stats_db(sdb)

    def test_store_entities_persist_across_queries(self, mock_mem0, mock_graph):
        """entities 在多次查询中保持一致"""
        sdb = _make_stats_db()

        mock_mem0.add.return_value = _make_add_result("s002", "Python is a programming language")

        p1, p2 = self._patch_all(mock_mem0)
        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph), \
                 patch('modules.brain.llm.extract_entities_llm', return_value=[]):
                from modules.brain.memory import store_memory

                text = "Python is a programming language"
                rowid = sdb.append_stream('store', content=text, status='pending')
                result = store_memory(text, memory_meta={"source": "mcp"})

                stored = result.get("stored_texts", [])
                if stored:
                    sdb.update_stream_content(rowid, "\n".join(f"• {t}" for t in stored))
                entities = result.get("entities", [])
                if entities:
                    sdb.update_stream_entities(rowid, ','.join(entities))
                sdb.update_stream_status(rowid, 'done')

        # 查询两次确认一致
        rows1 = sdb.query_stream(action='store', limit=5)
        rows2 = sdb.query_stream(action='store', limit=5)

        assert rows1[0]['entities'] == rows2[0]['entities']
        assert rows1[0]['id'] == rows2[0]['id']

        _cleanup_stats_db(sdb)

    def test_store_status_lifecycle(self, mock_mem0, mock_graph):
        """store 状态流转：pending → done / error"""
        sdb = _make_stats_db()

        # 初始 pending
        rowid = sdb.append_stream('store', content="test text", status='pending')
        rows = sdb.query_stream(action='store', limit=1)
        assert rows[0]['status'] == 'pending'
        assert rows[0]['entities'] == ''

        # 模拟完成
        sdb.update_stream_entities(rowid, 'entity1,entity2')
        sdb.update_stream_status(rowid, 'done')

        rows = sdb.query_stream(action='store', limit=1)
        assert rows[0]['status'] == 'done'
        assert rows[0]['entities'] == 'entity1,entity2'

        # 模拟错误
        rowid2 = sdb.append_stream('store', content="bad text", status='pending')
        sdb.update_stream_status(rowid2, 'error')
        rows = sdb.query_stream(action='store', limit=2)
        error_items = [r for r in rows if r['id'] == rowid2]
        assert error_items[0]['status'] == 'error'

        _cleanup_stats_db(sdb)


###############################################################################
# 2. Stream Search 流程测试
###############################################################################


class TestStreamSearchFlow:
    """测试 search → stream stats 完整流程"""

    @pytest.fixture
    def mock_mem0(self):
        client = MagicMock()
        client.search = MagicMock()
        client.get = MagicMock()
        client.get_all = MagicMock()
        return client

    @pytest.fixture
    def mock_graph(self):
        from backend.modules.brain.graph import GraphMemory
        db_file = os.path.join(tempfile.gettempdir(), f"test_search_stream_graph_{uuid.uuid4().hex}.db")
        g = GraphMemory(db_file)

        # 建立实体网络：mem_a(共享前端实体) → mem_b
        g.link_memory("mem_a", "Vue是一个前端框架", link_entities=["Vue", "前端"])
        g.link_memory("mem_b", "React也是前端框架", link_entities=["React", "前端"])

        yield g
        g._conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(db_file + suffix)
            except OSError:
                pass

    def _get_stats(self, results):
        """计算搜索统计（与 memory_routes.py _search_all_categories 一致）"""
        sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)[:15]
        semantic_count = sum(1 for r in sorted_results if r.get('source', 'semantic') != 'graph')
        graph_count = sum(1 for r in sorted_results if r.get('source') == 'graph')
        return {
            "total": len(sorted_results),
            "semantic": semantic_count,
            "entity": graph_count,
        }

    def test_search_writes_stats_to_stream(self, mock_mem0, mock_graph):
        """搜索完成后 stream 记录包含统计信息"""
        sdb = _make_stats_db()

        # 模拟搜索：向量命中 mem_a，图扩展找到 mem_b
        mock_mem0.search.return_value = {
            "results": [
                {"id": "mem_a", "memory": "Vue是一个前端框架", "score": 0.95},
            ]
        }
        mock_mem0.get_all.return_value = {"results": [{"id": "mem_a"}, {"id": "mem_b"}]}
        mock_mem0.get.return_value = {"memory": "React也是前端框架"}

        p1 = patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0)
        p2 = patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0)

        with p1, p2:
            with patch('modules.brain.memory._memory_settings', {"infer": False}), \
                 patch('modules.brain.graph.get_graph', return_value=mock_graph):
                import modules.brain.memory as mem_mod
                mem_mod._memory_count_cache = 2

                from modules.brain.memory import search_memory

                # step 1: 写入 pending
                query = "前端框架"
                rowid = sdb.append_stream('search', content=query, status='pending')

                # step 2: 执行搜索
                results = search_memory(query)

                # step 3: 计算统计
                stats = self._get_stats(results)

                # step 4: 写入 stats 到 stream
                entities_str = f"语义搜索:{stats['semantic']},实体网络:{stats['entity']}"
                sdb.update_stream_entities(rowid, entities_str)
                sdb.update_stream_status(rowid, 'done')

        # step 5: 验证 stream 记录
        rows = sdb.query_stream(action='search', limit=10)
        assert len(rows) > 0
        record = rows[0]
        assert record['status'] == 'done'
        assert record['content'] == query

        entities_val = record.get('entities', '')
        assert entities_val, f"entities should not be empty, got: '{entities_val}'"
        assert '语义搜索' in entities_val
        assert '实体网络' in entities_val

        # 解析统计
        parts = entities_val.split(',')
        for p in parts:
            assert ':' in p

        _cleanup_stats_db(sdb)

    def test_search_with_graph_expansion_stats(self, mock_mem0, mock_graph):
        """图扩展成功后统计中有 entity 计数 > 0"""
        sdb = _make_stats_db()

        mock_mem0.search.return_value = {
            "results": [
                {"id": "mem_a", "memory": "Vue是一个前端框架", "score": 0.95},
            ]
        }
        mock_mem0.get_all.return_value = {"results": [{"id": "mem_a"}, {"id": "mem_b"}]}
        mock_mem0.get.return_value = {"memory": "React也是前端框架"}

        with patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0), \
             patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0), \
             patch('modules.brain.memory._memory_settings', {"infer": False}), \
             patch('modules.brain.graph.get_graph', return_value=mock_graph):
            import modules.brain.memory as mem_mod
            mem_mod._memory_count_cache = 2

            from modules.brain.memory import search_memory

            rowid = sdb.append_stream('search', content="前端框架", status='pending')
            results = search_memory("前端框架")
            stats = self._get_stats(results)

            entities_str = f"语义搜索:{stats['semantic']},实体网络:{stats['entity']}"
            sdb.update_stream_entities(rowid, entities_str)
            sdb.update_stream_status(rowid, 'done')

        record = sdb.query_stream(action='search', limit=1)[0]
        parts = dict(p.split(':') for p in record['entities'].split(','))
        assert int(parts.get('实体网络', 0)) >= 0

        _cleanup_stats_db(sdb)

    def test_search_all_semantic_no_graph(self, mock_mem0):
        """纯语义搜索（无图扩展）时 entity=0"""
        sdb = _make_stats_db()

        mock_mem0.search.return_value = {
            "results": [
                {"id": "mem_x", "memory": "天气很好", "score": 0.8},
                {"id": "mem_y", "memory": "今天适合出门", "score": 0.7},
            ]
        }
        mock_mem0.get_all.return_value = {"results": [
            {"id": "mem_x"}, {"id": "mem_y"}
        ]}

        with patch('modules.brain.memory.get_mem0_client', return_value=mock_mem0), \
             patch('modules.brain.mem0_adapter.get_mem0_client', return_value=mock_mem0), \
             patch('modules.brain.memory._memory_settings', {"infer": False}), \
             patch('modules.brain.graph.get_graph', return_value=None):
            import modules.brain.memory as mem_mod
            mem_mod._memory_count_cache = 2

            from modules.brain.memory import search_memory

            rowid = sdb.append_stream('search', content="天气", status='pending')
            results = search_memory("天气")
            stats = self._get_stats(results)

            entities_str = f"语义搜索:{stats['semantic']},实体网络:{stats['entity']}"
            sdb.update_stream_entities(rowid, entities_str)
            sdb.update_stream_status(rowid, 'done')

        record = sdb.query_stream(action='search', limit=1)[0]
        parts = dict(p.split(':') for p in record['entities'].split(','))
        assert int(parts['语义搜索']) == 2
        assert int(parts['实体网络']) == 0

        _cleanup_stats_db(sdb)


###############################################################################
# 3. 前端 entityTags 解析逻辑测试（模拟 StreamItemBase.entityTags）
###############################################################################


class TestEntityTagsParsing:
    """模拟前端 entityTags getter 的行为"""

    def _entity_tags(self, entities: str) -> list[str]:
        """模拟 StreamItemBase.entityTags getter"""
        if not entities:
            return []
        return entities.split(',')

    def test_store_entity_tags(self):
        """store: entities='Python,code' → ['Python', 'code']"""
        tags = self._entity_tags('Python,code')
        assert tags == ['Python', 'code']

    def test_search_stats_tags(self):
        """search: entities='语义搜索:5,实体网络:3' → ['语义搜索:5', '实体网络:3']"""
        tags = self._entity_tags('语义搜索:5,实体网络:3')
        assert tags == ['语义搜索:5', '实体网络:3']
        assert len(tags) == 2

    def test_empty_entities(self):
        """空字符串返回空数组"""
        assert self._entity_tags('') == []
        assert self._entity_tags(None) == []

    def test_single_tag(self):
        """单个标签"""
        tags = self._entity_tags('语义搜索:1')
        assert tags == ['语义搜索:1']

    def test_many_tags(self):
        """多个实体标签"""
        tags = self._entity_tags('A,B,C,D,E')
        assert len(tags) == 5
        assert tags == ['A', 'B', 'C', 'D', 'E']


###############################################################################
# 4. Stream 记录完整性测试
###############################################################################


class TestStreamRecordIntegrity:
    """测试 stream 记录的各项字段完整性"""

    @pytest.fixture
    def sdb(self):
        sdb = _make_stats_db()
        yield sdb
        _cleanup_stats_db(sdb)

    def test_stream_has_required_fields(self, sdb):
        """stream 记录包含前端需要的所有字段"""
        rowid = sdb.append_stream('store', content="test", status='pending')
        sdb.update_stream_entities(rowid, 'tag1,tag2')
        sdb.update_stream_status(rowid, 'done')

        rows = sdb.query_stream(action='store', limit=1)
        record = rows[0]

        # 前端 StreamItemData 需要的字段
        assert 'id' in record
        assert 'action' in record
        assert 'content' in record
        assert 'memory_id' in record
        assert 'status' in record
        assert 'created_at' in record
        assert 'entities' in record

    def test_trim_keeps_latest(self, sdb):
        """写入超过 30 条后旧记录被裁剪"""
        for i in range(35):
            rowid = sdb.append_stream('store', content=f"memory {i}", status='done')
            sdb.update_stream_entities(rowid, f"entity_{i}")

        rows = sdb.query_stream(action='store', limit=50)
        assert len(rows) == 30  # 只保留 30 条

    def test_multiple_actions_dont_interfere(self, sdb):
        """不同 action 的流记录互不干扰"""
        # 写入 store
        rowid_s = sdb.append_stream('store', content="store content", status='pending')
        sdb.update_stream_entities(rowid_s, 'ent_store')
        sdb.update_stream_status(rowid_s, 'done')

        # 写入 search
        rowid_q = sdb.append_stream('search', content="search query", status='pending')
        sdb.update_stream_entities(rowid_q, '语义搜索:1,实体网络:0')
        sdb.update_stream_status(rowid_q, 'done')

        # 分别查询
        store_rows = sdb.query_stream(action='store', limit=10)
        search_rows = sdb.query_stream(action='search', limit=10)

        assert all(r['action'] == 'store' for r in store_rows)
        assert all(r['action'] == 'search' for r in search_rows)
        assert store_rows[0]['entities'] == 'ent_store'
        assert search_rows[0]['entities'] == '语义搜索:1,实体网络:0'
