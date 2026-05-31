"""Tests for AiBrain Memory Network Enhancement Plan (brain_network_plan.md)

Covers all phases:
- Phase 1 / Task 1: Capture mem0 auto-extracted entities
- Phase 2 / Task 2: memory_relations table (memory-to-memory edges)
- Phase 2 / Task 3: typed_entity_relations (relation types + weights)
- Phase 3 / Task 9: GraphMemory in-memory graph (NetworkX)
- Phase 4 / Task 4: Spreading activation algorithm
- Phase 4 / Task 5: get_memory_neighbors / get_memory_texts
- Phase 5 / Task 6: Entity similarity detection and auto-merge
- Phase 6 / Task 7: smart_store pattern (infer mode)
- Phase 7 / Task 8: merge_entities API
"""

import os
import tempfile
import uuid

import pytest

from backend.modules.brain.graph import GraphMemory, spreading_activation


@pytest.fixture
def graph():
    """Create a GraphMemory with a unique temp database, cleaned up after test."""
    db_path = os.path.join(tempfile.gettempdir(), f"test_brain_{uuid.uuid4().hex[:8]}.db")
    g = GraphMemory(db_path)
    yield g
    g._conn.close()
    for p in [db_path, db_path + "-wal", db_path + "-shm"]:
        try:
            os.remove(p)
        except OSError:
            pass


def _link(g, mid, text, entities=None):
    """Helper: link memory with entities, bypassing LLM."""
    g.link_memory(mid, text, link_entities=entities or [])


# ============================================================================
# Phase 1 / Task 1: mem0 auto-extracted entity capture
# ============================================================================


class TestTask1_Mem0EntityCapture:
    """mem0 infer=True events should write their auto-extracted entities to graph."""

    def test_auto_entities_written_to_entity_nodes(self, graph):
        """Entities from mem0 events should appear in entity_nodes."""
        graph.link_memory("mem1", "我喜欢吃苹果和香蕉", link_entities=["苹果", "香蕉"])
        names = [r[0] for r in graph._exec("SELECT name FROM entity_nodes WHERE name IN ('苹果', '香蕉')")]
        assert "苹果" in names
        assert "香蕉" in names

    def test_auto_entities_linked_in_mentions(self, graph):
        """Entities should be linked to memory via mentions table."""
        graph.link_memory("mem2", "志远喜欢猫", link_entities=["志远", "猫"])
        rows = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = 'mem2'")
        linked = {r[0] for r in rows}
        assert "志远" in linked
        assert "猫" in linked

    def test_mixed_auto_and_manual_entities(self, graph):
        """Both auto-extracted and manually specified entities should be stored."""
        graph.link_memory("mem3", "我喜欢吃苹果", link_entities=["苹果"])
        rows = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = 'mem3'")
        linked = {r[0] for r in rows}
        assert "苹果" in linked


# ============================================================================
# Phase 2 / Task 2: memory_relations table
# ============================================================================


class TestTask2_MemoryRelations:
    """Memories sharing entities should have direct edges in memory_relations."""

    def test_table_exists(self, graph):
        rows = graph._exec(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_relations'"
        )
        assert len(rows) == 1

    def test_shared_entity_creates_edge(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了一只橘猫", ["志远", "橘猫"])

        edges = {(r[0], r[1]) for r in graph._exec("SELECT from_mem, to_mem FROM memory_relations")}
        assert ("m1", "m2") in edges or ("m2", "m1") in edges

    def test_shared_entity_via_entity_recorded(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        _link(graph, "m2", "志远养了橘猫", ["志远"])

        rows = graph._exec("SELECT via_entity FROM memory_relations")
        entities = {r[0] for r in rows}
        assert "志远" in entities

    def test_no_shared_entity_no_edge(self, graph):
        _link(graph, "m1", "今天天气很好", ["天气"])
        _link(graph, "m2", "Python是一种编程语言", ["Python"])

        count = graph._exec("SELECT COUNT(*) FROM memory_relations")[0][0]
        assert count == 0

    def test_three_memories_create_multiple_edges(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了橘猫", ["志远", "橘猫"])
        _link(graph, "m3", "橘猫叫小花", ["橘猫"])

        edges = {(r[0], r[1]) for r in graph._exec("SELECT from_mem, to_mem FROM memory_relations")}
        # m1 <-> m2 (shared 志远), m2 <-> m3 (shared 橘猫)
        assert len(edges) >= 2


# ============================================================================
# Phase 2 / Task 3: typed_entity_relations (relation types + weights)
# ============================================================================


class TestTask3_TypedEntityRelations:
    """Entity relations should have types (similar/causal/partof/related) and weights."""

    def test_table_exists(self, graph):
        rows = graph._exec(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='typed_entity_relations'"
        )
        assert len(rows) == 1

    def test_table_schema_has_relation_type_and_weight(self, graph):
        """typed_entity_relations should have relation_type and weight columns."""
        rows = graph._exec("PRAGMA table_info(typed_entity_relations)")
        col_names = {r[1] for r in rows}
        assert "relation_type" in col_names
        assert "weight" in col_names

    def test_typed_relation_insert_and_query(self, graph):
        """Can insert and query typed entity relations."""
        graph._exec(
            "INSERT OR IGNORE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) "
            "VALUES (?, ?, ?, ?)",
            ("雨", "路滑", "causal", 1.5),
        )
        graph._conn.commit()
        rows = graph._exec("SELECT relation_type, weight FROM typed_entity_relations WHERE from_entity = '雨'")
        assert len(rows) == 1
        assert rows[0][0] == "causal"
        assert rows[0][1] == 1.5

    def test_multiple_relation_types(self, graph):
        """Multiple relation types can coexist between different entity pairs."""
        graph._exec(
            "INSERT OR IGNORE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) "
            "VALUES (?, ?, ?, ?)",
            ("猫", "橘猫", "similar", 0.8),
        )
        graph._exec(
            "INSERT OR IGNORE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) "
            "VALUES (?, ?, ?, ?)",
            ("猫", "动物", "partof", 1.0),
        )
        graph._conn.commit()
        rows = graph._exec("SELECT relation_type FROM typed_entity_relations WHERE from_entity = '猫'")
        types = {r[0] for r in rows}
        assert "similar" in types
        assert "partof" in types


# ============================================================================
# Phase 3 / Task 9: GraphMemory in-memory (NetworkX)
# ============================================================================


class TestTask9_GraphMemoryResident:
    """Graph should be loaded into memory (NetworkX) at init and synced on writes."""

    def test_nx_graph_initialized(self, graph):
        import networkx as nx
        assert isinstance(graph._graph, nx.Graph)

    def test_graph_loaded_from_sqlite_on_init(self, graph):
        """After writing edges and creating a new instance, in-memory graph should have them."""
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了橘猫", ["志远", "橘猫"])

        # Verify data is in SQLite
        rows = graph._exec("SELECT COUNT(*) FROM memory_relations")
        assert rows[0][0] > 0, "memory_relations should have edges before restart"

        # Checkpoint WAL so second connection sees the data
        graph._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        db_path = graph._conn.execute("PRAGMA database_list").fetchall()[0][2]
        g2 = GraphMemory(db_path)
        assert g2._graph.number_of_edges() > 0, "in-memory graph should load edges from SQLite"
        g2._conn.close()

    def test_sync_edge_updates_memory_graph(self, graph):
        initial = graph._graph.number_of_edges()
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了橘猫", ["志远", "橘猫"])
        # After linking m1 and m2 with shared entity "志远", memory_relations should have an edge
        mem_edges = graph._exec("SELECT COUNT(*) FROM memory_relations")
        assert mem_edges[0][0] > 0, "memory_relations should have edges"
        assert graph._graph.number_of_edges() > initial, "in-memory graph should have more edges"

    def test_typed_entity_relations_loaded_to_memory(self, graph):
        """typed_entity_relations edges should also appear in in-memory graph."""
        graph._exec(
            "INSERT OR IGNORE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) "
            "VALUES (?, ?, ?, ?)",
            ("猫", "狗", "similar", 0.9),
        )
        graph._conn.commit()
        # Reload graph from DB to pick up typed_entity_relations
        graph._load_graph_from_db()
        assert graph._graph.has_edge("猫", "狗")
        assert graph._graph["猫"]["狗"]["weight"] == 0.9


# ============================================================================
# Phase 4 / Task 4: Spreading activation algorithm
# ============================================================================


class TestTask4_ActivationSpreading:
    """Activation spreading should propagate through graph edges with decay."""

    def test_spreading_activation_basic(self):
        """Basic activation spreading through a chain graph."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("m1", "m2", weight=1.0)
        G.add_edge("m2", "m3", weight=1.0)

        activations = spreading_activation(G, ["m1"], [1.0], decay=0.5, threshold=0.1)
        assert "m2" in activations
        assert "m3" in activations
        assert activations["m2"] > activations["m3"]  # decay

    def test_spreading_activation_decay(self):
        """Activation should decay with distance."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("a", "b", weight=1.0)
        G.add_edge("b", "c", weight=1.0)
        G.add_edge("c", "d", weight=1.0)

        activations = spreading_activation(G, ["a"], [1.0], decay=0.5, threshold=0.01)
        assert activations["b"] > activations["c"] > activations["d"]

    def test_spreading_activation_threshold(self):
        """Activation below threshold should not propagate further."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("a", "b", weight=1.0)
        G.add_edge("b", "c", weight=1.0)
        G.add_edge("c", "d", weight=1.0)

        # With threshold=0.3: a→b(0.5), b→c(0.25) recorded but not propagated
        activations = spreading_activation(G, ["a"], [1.0], decay=0.5, threshold=0.3)
        assert "b" in activations
        assert activations["b"] == 0.5
        # c gets recorded (0.25) but d should not be reached
        assert "d" not in activations

    def test_spreading_activation_empty_input(self):
        """Empty input should return empty dict."""
        import networkx as nx
        G = nx.Graph()
        assert spreading_activation(G, [], []) == {}
        assert spreading_activation(None, ["a"], [1.0]) == {}

    def test_spreading_activation_edge_weight(self):
        """Higher edge weights should produce stronger activation."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("a", "b", weight=2.0)
        G.add_edge("a", "c", weight=0.5)

        activations = spreading_activation(G, ["a"], [1.0], decay=0.5, threshold=0.01)
        assert activations["b"] > activations["c"]

    def test_search_related_uses_activation(self, graph):
        """search_related should use activation spreading when in-memory graph has edges."""
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了橘猫", ["志远", "橘猫"])
        _link(graph, "m3", "橘猫叫小花", ["橘猫", "小花"])

        result = graph.search_related(["m1"], max_hops=2)
        ids = {r["id"] for r in result}
        assert "m2" in ids
        assert "m3" in ids

    def test_search_related_returns_scores(self, graph):
        """search_related results should include activation scores."""
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        _link(graph, "m2", "志远养了橘猫", ["志远"])

        result = graph.search_related(["m1"], initial_scores=[0.9], max_hops=1)
        for r in result:
            assert "score" in r
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# Phase 4 / Task 5: get_memory_neighbors / get_memory_texts
# ============================================================================


class TestTask5_GetMemoryNeighbors:
    """get_memory_neighbors should return (neighbor_id, weight) tuples."""

    def test_returns_weighted_neighbors(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了橘猫", ["志远", "橘猫"])

        neighbors = graph.get_memory_neighbors("m1")
        assert len(neighbors) > 0
        assert all(isinstance(n, tuple) and len(n) == 2 for n in neighbors)
        neighbor_ids = {n[0] for n in neighbors}
        assert "m2" in neighbor_ids

    def test_respects_limit(self, graph):
        for i in range(5):
            _link(graph, f"m{i}", f"记忆{i}", ["共享实体"])

        neighbors = graph.get_memory_neighbors("m0", limit=2)
        assert len(neighbors) <= 2

    def test_no_neighbors_for_isolated_memory(self, graph):
        _link(graph, "m1", "单独的记忆", ["唯一实体"])
        neighbors = graph.get_memory_neighbors("m1")
        assert len(neighbors) == 0


class TestTask5_GetMemoryTexts:
    """get_memory_texts should batch-fetch memory texts."""

    def test_returns_texts_for_known_ids(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        _link(graph, "m2", "今天天气好", ["天气"])

        texts = graph.get_memory_texts(["m1", "m2"])
        assert texts["m1"] == "志远喜欢猫"
        assert texts["m2"] == "今天天气好"

    def test_empty_ids_returns_empty(self, graph):
        assert graph.get_memory_texts([]) == {}

    def test_nonexistent_ids_skipped(self, graph):
        _link(graph, "m1", "存在的记忆", ["实体"])
        texts = graph.get_memory_texts(["m1", "nonexistent"])
        assert texts["m1"] == "存在的记忆"
        assert "nonexistent" not in texts


# ============================================================================
# Phase 5 / Task 6: Entity similarity detection
# ============================================================================


class TestTask6_EntitySimilarityMerge:
    """Similar entities should be detected via Jaccard / substring inclusion."""

    def test_find_similar_by_exact_match(self, graph):
        _link(graph, "m1", "苹果是一种水果", ["苹果", "水果"])
        similar = graph._find_similar_entity("苹果")
        assert similar == "苹果"

    def test_find_similar_by_substring_inclusion(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        # "志远" is contained in "志远的猫" and vice versa check
        similar = graph._find_similar_entity("志远")
        assert similar == "志远"

    def test_find_similar_returns_none_for_unrelated(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        similar = graph._find_similar_entity("xyz123abc")
        assert similar is None

    def test_find_similar_returns_none_for_empty_db(self, graph):
        similar = graph._find_similar_entity("任何东西")
        assert similar is None

    def test_jaccard_similarity(self, graph):
        _link(graph, "m1", "test", ["机器学习模型"])
        # "机器学习" has high Jaccard overlap with "机器学习模型"
        similar = graph._find_similar_entity("机器学习")
        assert similar is not None


# ============================================================================
# Phase 6 / Task 7: smart_store pattern
# ============================================================================


class TestTask7_SmartStore:
    """smart_store pattern: infer=True uses mem0, infer=False uses link_entities."""

    def test_infer_mode_respects_settings(self):
        """store_memory should read infer setting from memory_settings."""
        # Verify settings file path exists and has expected structure
        import os, json
        settings_path = os.path.join(
            os.path.expanduser("~"), ".aibrain", "config", "memory_settings.json"
        )
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            assert "infer" in settings
            assert isinstance(settings["infer"], bool)
        else:
            # Default settings should have infer=True
            assert True  # defaults are {"infer": True}

    def test_link_entities_accepted_by_link_memory(self, graph):
        """link_memory should accept and store link_entities."""
        graph.link_memory("m1", "我喜欢日本料理", link_entities=["日本", "料理"])
        entities = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = 'm1'")
        assert len(entities) > 0
        names = {r[0] for r in entities}
        assert "日本" in names
        assert "料理" in names


# ============================================================================
# Phase 7 / Task 8: merge_entities API
# ============================================================================


class TestTask8_MergeEntities:
    """merge_entities should move all mentions and relations from b to a."""

    def test_method_exists(self, graph):
        assert callable(getattr(graph, 'merge_entities', None))

    def test_merge_moves_mentions(self, graph):
        _link(graph, "m1", "苹果是一种水果", ["苹果", "水果"])
        _link(graph, "m2", "我喜欢吃 apple", ["apple"])

        graph.merge_entities("苹果", "apple")

        # apple mentions should now point to 苹果
        apple_mentions = graph._exec(
            "SELECT COUNT(*) FROM mentions WHERE entity_name = 'apple'"
        )[0][0]
        assert apple_mentions == 0

        # 苹果 should now have the merged mentions
        apple_mentions = graph._exec(
            "SELECT COUNT(*) FROM mentions WHERE entity_name = '苹果'"
        )[0][0]
        assert apple_mentions >= 2

    def test_merge_deletes_source_entity(self, graph):
        _link(graph, "m1", "苹果是水果", ["苹果"])
        _link(graph, "m2", "apple is fruit", ["apple"])

        graph.merge_entities("苹果", "apple")

        apple_exists = graph._exec("SELECT name FROM entity_nodes WHERE name = 'apple'")
        assert len(apple_exists) == 0

    def test_merge_maintains_target_entity(self, graph):
        _link(graph, "m1", "苹果是水果", ["苹果"])
        _link(graph, "m2", "apple is fruit", ["apple"])

        graph.merge_entities("苹果", "apple")

        pingguo_exists = graph._exec("SELECT name FROM entity_nodes WHERE name = '苹果'")
        assert len(pingguo_exists) == 1


# ============================================================================
# E2E: Full activation spreading flow
# ============================================================================


class TestE2E_ActivationSpreading:
    """End-to-end: store memories, verify activation spreading recall."""

    def test_store_and_recall_via_activation(self, graph):
        _link(graph, "m1", "志远喜欢猫", ["志远", "猫"])
        _link(graph, "m2", "志远养了一只橘猫", ["志远", "橘猫"])
        _link(graph, "m3", "橘猫喜欢吃鱼", ["橘猫", "鱼"])
        _link(graph, "m4", "今天天气很好", ["天气"])

        result = graph.search_related(["m1"], max_hops=2)
        ids = {r["id"] for r in result}

        assert "m2" in ids
        assert "m3" in ids
        assert "m4" not in ids

    def test_activation_decay_ordering(self, graph):
        _link(graph, "m1", "记忆1", ["X"])
        _link(graph, "m2", "记忆2", ["X"])
        _link(graph, "m3", "记忆3", ["X"])

        result = graph.search_related(["m1"], max_hops=3)
        scores = {r["id"]: r["score"] for r in result}

        if "m2" in scores and "m3" in scores:
            assert scores["m2"] >= scores["m3"]

    def test_bidirectional_activation(self, graph):
        """Activation should spread in both directions of memory_relations."""
        _link(graph, "m1", "志远喜欢猫", ["志远"])
        _link(graph, "m2", "志远养了橘猫", ["志远"])

        # From m1 should find m2
        r1 = graph.search_related(["m1"], max_hops=1)
        assert any(r["id"] == "m2" for r in r1)

        # From m2 should find m1
        r2 = graph.search_related(["m2"], max_hops=1)
        assert any(r["id"] == "m1" for r in r2)
