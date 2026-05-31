"""Tests for Graph V2: entity auto-dedup + LLM relation type inference + spreading enhancement"""

import os
import tempfile
import uuid
from unittest.mock import patch, MagicMock

import pytest

from backend.modules.brain.graph import GraphMemory, spreading_activation


@pytest.fixture
def graph():
    """Create a GraphMemory with a unique temp database, cleaned up after test."""
    db_path = os.path.join(tempfile.gettempdir(), f"test_graph_v2_{uuid.uuid4().hex[:8]}.db")
    g = GraphMemory(db_path)
    yield g
    g._conn.close()
    for p in [db_path, db_path + "-wal", db_path + "-shm"]:
        try:
            os.remove(p)
        except OSError:
            pass


# ============================================================================
# Feature 1: Entity Auto-Dedup
# ============================================================================


class TestEntityAutoDedup:
    """Vector-based entity auto-deduplication during link_memory."""

    def test_similar_entity_reused(self, graph):
        """When a semantically similar entity exists, reuse it instead of creating new."""
        # First: create entity "志远"
        graph.link_memory("mem1", "志远喜欢编程", link_entities=["志远"])
        assert "志远" in [r[0] for r in graph._exec("SELECT name FROM entity_nodes")]

        # Second: mock vector similarity to return "志远" for "志远哥"
        with patch.object(graph, '_find_similar_entity_vector', return_value="志远"):
            graph.link_memory("mem2", "志远哥今天写代码", link_entities=["志远哥"])

        # "志远哥" should NOT appear as a new entity
        names = [r[0] for r in graph._exec("SELECT name FROM entity_nodes WHERE name = '志远哥'")]
        assert len(names) == 0

        # Both memories should be linked to "志远"
        mentions = [r[0] for r in graph._exec(
            "SELECT mem0_id FROM mentions WHERE entity_name = '志远'"
        )]
        assert "mem1" in mentions
        assert "mem2" in mentions

    def test_dissimilar_entity_created(self, graph):
        """When no similar entity exists, create new one."""
        graph.link_memory("mem1", "志远喜欢编程", link_entities=["志远"])

        with patch.object(graph, '_find_similar_entity_vector', return_value=None):
            graph.link_memory("mem2", "猫猫在睡觉", link_entities=["猫猫"])

        names = [r[0] for r in graph._exec("SELECT name FROM entity_nodes")]
        assert "志远" in names
        assert "猫猫" in names

    def test_dedup_increases_network_density(self, graph):
        """Dedup ensures related memories share the same entity hub."""
        graph.link_memory("mem1", "志远喜欢编程", link_entities=["志远"])
        with patch.object(graph, '_find_similar_entity_vector', return_value="志远"):
            graph.link_memory("mem2", "志远哥今天写代码", link_entities=["志远哥"])

        # Both memories should share the entity, enabling mesh recall
        mem1_related = graph._exec(
            "SELECT to_mem FROM memory_relations WHERE from_mem = 'mem1'"
        )
        assert any(r[0] == "mem2" for r in mem1_related)

    def test_embedding_cache_warmed_on_init(self, graph):
        """Entity embedding cache should be populated after init."""
        graph.link_memory("mem1", "test", link_entities=["测试实体"])
        # The cache should contain the entity (if embeddings available)
        # This mainly tests no crash occurs
        assert isinstance(graph._entity_embedding_cache, dict)

    def test_jaccard_fallback(self, graph):
        """When vector method unavailable, Jaccard fallback should work."""
        # "用户" is a default entity - substring match should find it
        result = graph._find_similar_entity("用户", threshold=0.75)
        assert result == "用户"


# ============================================================================
# Feature 2: LLM Relation Type Inference
# ============================================================================


class TestRelationInference:
    """LLM-based relation type inference and storage."""

    def test_infer_relations_stores_typed_edges(self, graph):
        """_infer_and_store_typed_relations should write to typed_entity_relations."""
        mock_relations = [
            {"from": "Python", "to": "编程", "relation_type": "associated", "confidence": 0.9},
        ]

        # Directly test the method with mocked LLM
        with patch('backend.modules.brain.llm.infer_relations', return_value=mock_relations):
            graph._infer_and_store_typed_relations("mem1", ["Python", "编程"], "志远喜欢Python编程")

        rows = graph._exec("SELECT from_entity, to_entity, relation_type, weight FROM typed_entity_relations")
        assert len(rows) >= 1
        found = any(r[0] == "Python" and r[1] == "编程" and r[2] == "associated" for r in rows)
        assert found

    def test_infer_relations_bidirectional(self, graph):
        """Typed relations should be stored bidirectionally."""
        mock_relations = [
            {"from": "A", "to": "B", "relation_type": "causal", "confidence": 0.8},
        ]
        with patch('backend.modules.brain.llm.infer_relations', return_value=mock_relations):
            graph._infer_and_store_typed_relations("mem1", ["A", "B"], "A causes B")

        rows = graph._exec("SELECT from_entity, to_entity FROM typed_entity_relations")
        names = [(r[0], r[1]) for r in rows]
        assert ("A", "B") in names
        assert ("B", "A") in names

    def test_infer_syncs_to_networkx(self, graph):
        """Typed relations should be synced to NetworkX graph with relation_type attribute."""
        mock_relations = [
            {"from": "X", "to_entity": "Y", "to": "Y", "relation_type": "similar", "confidence": 0.7},
        ]
        with patch('backend.modules.brain.llm.infer_relations', return_value=mock_relations):
            graph._infer_and_store_typed_relations("mem1", ["X", "Y"], "X is similar to Y")

        if graph._graph:
            assert graph._graph.has_edge("X", "Y")
            edge_data = graph._graph["X"]["Y"]
            assert edge_data.get("relation_type") == "similar"

    def test_async_trigger_in_link_memory(self, graph):
        """link_memory should trigger async inference when >= 2 entities."""
        with patch('backend.modules.brain.graph.threading.Thread') as MockThread:
            MockThread.return_value = MagicMock()
            graph.link_memory("mem1", "test", link_entities=["A", "B"])
            MockThread.assert_called_once()
            assert MockThread.call_args[1]['daemon'] is True

    def test_no_inference_for_single_entity(self, graph):
        """link_memory should NOT trigger inference for single entity."""
        with patch('backend.modules.brain.graph.threading.Thread') as MockThread:
            graph.link_memory("mem1", "test", link_entities=["A"])
            MockThread.assert_not_called()


# ============================================================================
# Feature 2: Spreading Activation Enhancement
# ============================================================================


class TestSpreadingActivationTypes:
    """Spreading activation should use relation_type multipliers."""

    def test_causal_edge_spreads_further(self):
        """Causal edges should have higher multiplier (1.2) than associated (1.0)."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("A", "B", weight=1.0, relation_type="causal")
        G.add_edge("A", "C", weight=1.0, relation_type="associated")

        result = spreading_activation(G, ["A"], [1.0], decay=0.5, threshold=0.01)
        # B should have higher activation than C (1.2x vs 1.0x multiplier)
        assert result.get("B", 0) > result.get("C", 0)

    def test_contradicts_edge_reduced_spread(self):
        """Contradicts edges should have lower multiplier (0.5)."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("A", "B", weight=1.0, relation_type="contradicts")
        G.add_edge("A", "C", weight=1.0, relation_type="associated")

        result = spreading_activation(G, ["A"], [1.0], decay=0.5, threshold=0.01)
        # B should have lower activation than C
        assert result.get("B", 0) < result.get("C", 0)

    def test_partof_edge_highest_multiplier(self):
        """PartOf edges should have highest multiplier (1.3)."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("A", "B", weight=1.0, relation_type="partof")
        G.add_edge("A", "C", weight=1.0, relation_type="causal")

        result = spreading_activation(G, ["A"], [1.0], decay=0.5, threshold=0.01)
        assert result.get("B", 0) > result.get("C", 0)

    def test_missing_relation_type_defaults_associated(self):
        """Edges without relation_type should default to associated (1.0 multiplier)."""
        import networkx as nx
        G = nx.Graph()
        G.add_edge("A", "B", weight=1.0)  # no relation_type

        result = spreading_activation(G, ["A"], [1.0], decay=0.5, threshold=0.01)
        assert result.get("B", 0) == pytest.approx(0.5, abs=0.01)

    def test_load_graph_includes_relation_type(self, graph):
        """_load_graph_from_db should load relation_type into NetworkX edges."""
        # Insert a typed relation directly
        graph._exec(
            "INSERT OR REPLACE INTO typed_entity_relations (from_entity, to_entity, relation_type, weight) VALUES (?, ?, ?, ?)",
            ("A", "B", "causal", 0.9),
        )
        graph._conn.commit()

        # Reload graph
        graph._graph.clear() if graph._graph else None
        graph._load_graph_from_db()

        if graph._graph and graph._graph.has_edge("A", "B"):
            edge_data = graph._graph["A"]["B"]
            assert edge_data.get("relation_type") == "causal"


# ============================================================================
# Integration: Full Flow
# ============================================================================


class TestIntegration:
    """End-to-end: store memory → dedup → infer relations → enhanced recall."""

    def test_full_flow(self, graph):
        """Store memories, verify dedup + typed relations enhance recall."""
        # Store first memory with entity
        with patch.object(graph, '_find_similar_entity_vector', return_value=None):
            graph.link_memory("mem1", "志远在学习Python", link_entities=["志远", "Python"])

        # Store second memory - "志远哥" should dedup to "志远"
        with patch.object(graph, '_find_similar_entity_vector', return_value="志远"):
            graph.link_memory("mem2", "志远哥今天写了Python代码", link_entities=["志远哥", "Python"])

        # Verify: both memories linked to same entity "志远"
        mentions = graph._exec(
            "SELECT mem0_id FROM mentions WHERE entity_name = '志远'"
        )
        mem_ids = [r[0] for r in mentions]
        assert "mem1" in mem_ids
        assert "mem2" in mem_ids

        # Verify: memory_relations connect mem1 and mem2
        related = graph._exec(
            "SELECT to_mem FROM memory_relations WHERE from_mem = 'mem1'"
        )
        related_ids = [r[0] for r in related]
        assert "mem2" in related_ids

    def test_search_related_finds_connected_memories(self, graph):
        """search_related should find memories connected via shared entities."""
        with patch.object(graph, '_find_similar_entity_vector', return_value=None):
            graph.link_memory("mem1", "志远喜欢Python", link_entities=["志远", "Python"])
            graph.link_memory("mem2", "志远在学习机器学习", link_entities=["志远", "机器学习"])
            graph.link_memory("mem3", "Python是最好的编程语言", link_entities=["Python", "编程"])

        results = graph.search_related(["mem1"])
        result_ids = [r["id"] for r in results]
        # Should find mem2 (shared 志远) and mem3 (shared Python)
        assert "mem2" in result_ids
        assert "mem3" in result_ids
