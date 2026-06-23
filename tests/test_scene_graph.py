"""情景图扩散（scene graph diffusion）单元测试

覆盖：
  FR-002 锚点建图 / FR-003 情景间扩散 / FR-004 情感与重要性加权
  FR-005 因果与教训联想（query 锚点命中）/ FR-008 扩散可解释(trace) / FR-011 图规模控制

纯 SQLite + 内存算法，不依赖 embed server / LLM / Qdrant（payload 用 monkeypatch 注入）。
"""
import os
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from modules.brain.memory.scene_graph import SceneGraph, _dedup_nodes
from modules.brain.memory import scene_diffusion as sd_mod
from modules.brain.memory.scene_diffusion import SceneDiffusion, _assemble_seeds


@pytest.fixture
def sg():
    """临时 DB 的 SceneGraph 实例"""
    db_path = os.path.join(tempfile.gettempdir(), "test_scene_graph.db")
    g = SceneGraph(db_path)
    yield g
    g._conn.close()
    for p in (db_path, db_path + "-wal", db_path + "-shm"):
        try:
            os.remove(p)
        except OSError:
            pass


def _diff_with(graph):
    """构造一个绑定到指定 graph 的 SceneDiffusion（绕过单例 __init__）"""
    d = SceneDiffusion.__new__(SceneDiffusion)
    d._graph = graph
    return d


# ── FR-002 锚点建图 ──────────────────────────────────────────


class TestAnchorLinking:
    def test_link_scene_creates_anchors_and_edges(self, sg):
        sg.link_scene(
            "s1",
            [{"name": "志远", "type": "person"}, {"name": "entity_relations", "type": "concept"}],
            affect={"intensity": 2.0},
            importance=0.8,
        )
        anchors = sg.get_scene_anchors("s1")
        assert {a["name"] for a in anchors} == {"志远", "entity_relations"}
        # person 锚点权重高于 concept
        by_name = {a["name"]: a for a in anchors}
        assert by_name["志远"]["weight"] > by_name["entity_relations"]["weight"]
        assert sg.find_anchor("志远")["type"] == "person"

    def test_role_from_node_type(self, sg):
        sg.link_scene(
            "s1",
            [{"name": "成就感", "type": "emotion"}, {"name": "AiBrain", "type": "goal"}],
            importance=0.5,
        )
        anchors = {a["name"]: a for a in sg.get_scene_anchors("s1")}
        assert anchors["成就感"]["role"] == "emotion"
        assert anchors["AiBrain"]["role"] == "goal"

    def test_link_scene_idempotent(self, sg):
        """重复 link 同一 scene 不产生重复边"""
        nodes = [{"name": "概念A", "type": "concept"}]
        sg.link_scene("s1", nodes, importance=0.5)
        sg.link_scene("s1", nodes, importance=0.5)
        assert len(sg.get_scene_anchors("s1")) == 1


# ── FR-003 / FR-004 共享锚点扩散 + 加权 ──────────────────────


class TestDiffusion:
    def test_shared_anchor_creates_edge_and_diffusion_finds_it(self, sg, monkeypatch):
        sg.link_scene("s1", [{"name": "entity_relations", "type": "concept"}], importance=0.8)
        sg.link_scene("s2", [{"name": "entity_relations", "type": "concept"}], importance=0.6)
        # s2 是 s1 的邻居
        neighbors = sg.get_scene_neighbors("s1")
        assert any(n["scene_id"] == "s2" for n in neighbors)

        # 语义命中 s1（payload 带 nodes），扩散应召回 s2
        sem = [{"id": "s1", "text": "理解entity_relations", "score": 0.9,
                "payload": {"nodes": [{"name": "entity_relations", "type": "concept"}]}}]
        monkeypatch.setattr(sd_mod, "_fetch_payloads",
                            lambda ids: {"s2": {"display_text": "顿悟关系激活",
                                                "importance": 0.6, "affect": {"intensity": 1.0}}})
        d = _diff_with(sg)
        results = d.search("entity_relations", sem, top_k=10)
        ids = [r["id"] for r in results]
        assert "s2" in ids
        # 种子 s1 自身被排除
        assert "s1" not in ids

    def test_high_importance_boosts_score(self, sg, monkeypatch):
        """高 importance 的候选得分更高（FR-004）"""
        sg.link_scene("seed", [{"name": "概念X", "type": "concept"}], importance=0.5)
        sg.link_scene("low", [{"name": "概念X", "type": "concept"}], importance=0.1)
        sg.link_scene("high", [{"name": "概念X", "type": "concept"}], importance=0.95)
        sem = [{"id": "seed", "text": "x", "score": 0.9,
                "payload": {"nodes": [{"name": "概念X", "type": "concept"}]}}]
        monkeypatch.setattr(sd_mod, "_fetch_payloads", lambda ids: {
            "low": {"display_text": "low", "importance": 0.1, "affect": {"intensity": 0}},
            "high": {"display_text": "high", "importance": 0.95, "affect": {"intensity": 2.0}},
        })
        d = _diff_with(sg)
        results = {r["id"]: r["score"] for r in d.search("概念X", sem, top_k=10)}
        assert results["high"] > results["low"]

    def test_trace_output(self, sg, monkeypatch):
        """扩散结果带可解释 trace（FR-008）"""
        sg.link_scene("s1", [{"name": "志远", "type": "person"}], importance=0.7)
        sg.link_scene("s2", [{"name": "志远", "type": "person"}], importance=0.7)
        sem = [{"id": "s1", "text": "志远讲解", "score": 0.9,
                "payload": {"nodes": [{"name": "志远", "type": "person"}]}}]
        monkeypatch.setattr(sd_mod, "_fetch_payloads",
                            lambda ids: {"s2": {"display_text": "s2", "importance": 0.5}})
        d = _diff_with(sg)
        results = d.search("志远", sem, top_k=10)
        s2 = next(r for r in results if r["id"] == "s2")
        tr = s2["trace"]
        assert tr["hop"] >= 1
        assert "志远" in tr["seed_nodes"]
        assert tr["relation_type"]  # 非空


# ── FR-005 query 锚点命中 ────────────────────────────────────


class TestQueryAnchorBoost:
    def test_query_anchor_match_boosts(self, sg, monkeypatch):
        """候选含 query 中出现的锚点时得分更高（FR-005 person/goal 锚点）"""
        sg.link_scene("seed", [{"name": "AiBrain", "type": "goal"}], importance=0.5)
        sg.link_scene("hit", [{"name": "AiBrain", "type": "goal"}], importance=0.5)
        sg.link_scene("miss", [{"name": "其它概念", "type": "concept"}], importance=0.5)
        # seed 与 hit 共享 AiBrain；seed 与 miss 也需共享某锚点才会被召回 → 给 seed 加 miss 的锚点
        sg.link_scene("seed", [{"name": "其它概念", "type": "concept"}], importance=0.5)
        sem = [{"id": "seed", "text": "AiBrain", "score": 0.9,
                "payload": {"nodes": [{"name": "AiBrain", "type": "goal"},
                                      {"name": "其它概念", "type": "concept"}]}}]
        monkeypatch.setattr(sd_mod, "_fetch_payloads", lambda ids: {
            sid: {"display_text": sid, "importance": 0.5, "affect": {"intensity": 0}}
            for sid in ids
        })
        d = _diff_with(sg)
        results = {r["id"]: r["score"] for r in d.search("AiBrain", sem, top_k=10)}
        # 两个都被召回，命中的 query 锚点得分更高
        assert results["hit"] > results["miss"]


# ── FR-011 图规模控制 ────────────────────────────────────────


class TestGraphScaleControl:
    def test_edge_limit_per_scene(self, sg):
        """单 scene 出边不超过 _MAX_EDGES_PER_SCENE"""
        from modules.brain.memory.scene_graph import _MAX_EDGES_PER_SCENE
        # seed 与 N 个 scene 共享同一锚点，应被限边
        sg.link_scene("seed", [{"name": "共享", "type": "concept"}], importance=0.5)
        for i in range(_MAX_EDGES_PER_SCENE + 5):
            sg.link_scene(f"s{i}", [{"name": "共享", "type": "concept"}], importance=0.5)
        neighbors = sg.get_scene_neighbors("seed", limit=100)
        assert len(neighbors) <= _MAX_EDGES_PER_SCENE

    def test_delete_scene_removes_edges(self, sg):
        sg.link_scene("s1", [{"name": "概念", "type": "concept"}], importance=0.5)
        sg.link_scene("s2", [{"name": "概念", "type": "concept"}], importance=0.5)
        assert any(n["scene_id"] == "s2" for n in sg.get_scene_neighbors("s1"))
        sg.delete_scene("s2")
        assert not any(n["scene_id"] == "s2" for n in sg.get_scene_neighbors("s1"))
        assert sg.get_scene_anchors("s2") == []


# ── 纯函数 ───────────────────────────────────────────────────


class TestPureHelpers:
    def test_assemble_seeds_from_payload_nodes(self):
        sem = [
            {"id": "a", "score": 0.8, "payload": {"nodes": [{"name": "x"}, {"name": "y"}]}},
            {"id": "b", "score": 0.4, "payload": {}},  # legacy 无 nodes
        ]
        scenes, anchors, scores = _assemble_seeds(sem)
        assert scenes == ["a", "b"]
        assert anchors == ["x", "y"]
        # 语义分归一化：a 最高 → 1.0
        assert scores["a"] == 1.0
        assert scores["b"] < scores["a"]

    def test_dedup_nodes_keeps_higher_rank_type(self):
        nodes = [
            {"name": "志远", "type": "concept"},
            {"name": "志远", "type": "person"},  # person 排名更高，应覆盖
            {"name": "x", "type": "concept"},
        ]
        out = {n["name"]: n["type"] for n in _dedup_nodes(nodes)}
        assert out["志远"] == "person"
        assert out["x"] == "concept"

    def test_assemble_seeds_empty(self):
        assert _assemble_seeds([]) == ([], [], {})


# ── 统计 ─────────────────────────────────────────────────────


class TestStats:
    def test_stats_counts(self, sg):
        sg.link_scene("s1", [{"name": "a", "type": "concept"}], importance=0.5)
        sg.link_scene("s2", [{"name": "a", "type": "concept"}], importance=0.5)
        stats = sg.get_stats()
        assert stats["scenes_indexed"] == 2
        assert stats["anchor_count"] == 1
        assert stats["scene_anchor_edges"] == 2
        assert stats["scene_scene_edges"] >= 2  # 双向
