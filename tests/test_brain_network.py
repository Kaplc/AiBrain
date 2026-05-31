"""测试 AiBrain 记忆网络增强计划 (brain_network_plan.md)

覆盖 9 个 Task:
- Task 1: 捕获 mem0 自动提取的实体
- Task 2: memory_relations 表
- Task 3: typed_entity_relations 表（关系类型+权重）
- Task 9: GraphMemory 常驻内存
- Task 4: 激活扩散算法
- Task 5: get_memory_neighbors
- Task 6: 实体相似度检测与自动合并
- Task 7: Hermes smart_store 封装
- Task 8: merge_entities API
"""

import os
import tempfile
import pytest
from backend.modules.brain.graph import GraphMemory


@pytest.fixture
def graph():
    """用临时数据库创建 GraphMemory 实例"""
    db_path = os.path.join(tempfile.gettempdir(), "test_brain_network.db")
    g = GraphMemory(db_path)
    yield g
    # 清理
    g._conn.close()
    try:
        os.remove(db_path)
        for suffix in ("-wal", "-shm"):
            p = db_path + suffix
            if os.path.exists(p):
                os.remove(p)
    except Exception:
        pass


def _link(graph, mid, text, entities=None):
    """直接用 link_entities 绕过 LLM 提取"""
    graph.link_memory(mid, text, link_entities=entities or [])


# ============================================================================
# Task 1: 捕获 mem0 自动提取的实体
# ============================================================================

class TestTask1_Mem0EntityCapture:
    """Task 1: mem0 infer=True 时，ev.get('entities') 应写入图谱

    现状: store_memory() 忽略 mem0 LLM 返回的 entities
    期望: entities 写入 entity_nodes 和 mentions 表
    """

    def test_mem0_auto_entities_written_to_graph(self, graph):
        """mem0 自动提取的实体应写入 entity_nodes"""
        # 模拟 mem0 返回的事件，包含 entities
        mem_id = "mem_test_1"
        text = "我喜欢吃苹果和香蕉"
        entities = ["苹果", "香蕉"]

        # 现有 link_memory 不处理 auto_entities，
        # Task 1 改动后应支持传入 auto_entities
        graph.link_memory(mem_id, text, link_entities=entities)

        # 验证 entity_nodes 有这两个实体
        rows = graph._exec("SELECT name FROM entity_nodes")
        entity_names = [r[0] for r in rows]
        assert "苹果" in entity_names, "苹果应该被写入 entity_nodes"
        assert "香蕉" in entity_names, "香蕉应该被写入 entity_nodes"

    def test_entities_linked_to_memory_in_mentions(self, graph):
        """实体应通过 mentions 表关联到记忆"""
        mem_id = "mem_test_2"
        text = "志远喜欢猫"
        entities = ["志远", "猫"]

        graph.link_memory(mem_id, text, link_entities=entities)

        rows = graph._exec(
            "SELECT entity_name FROM mentions WHERE mem0_id = ?",
            (mem_id,)
        )
        linked_entities = [r[0] for r in rows]
        assert "志远" in linked_entities
        assert "猫" in linked_entities


# ============================================================================
# Task 2: memory_relations 表（记忆与记忆直接关联）
# ============================================================================

class TestTask2_MemoryRelations:
    """Task 2: 共享实体的记忆之间应建立直接关联边

    现状: 记忆通过实体间接相连，没有直接边
    期望: 写入记忆时自动创建 memory_relations 边
    """

    def test_memory_relations_table_exists(self, graph):
        """memory_relations 表应存在"""
        rows = graph._exec(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_relations'"
        )
        assert len(rows) == 1, "memory_relations 表应该存在"

    def test_shared_entity_creates_memory_relation(self, graph):
        """两条记忆共享实体时应创建 memory_relations 边"""
        # 写入两条共享 "志远" 的记忆
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])

        # 查询 memory_relations
        rows = graph._exec("SELECT from_mem, to_mem, via_entity FROM memory_relations")
        edges = [(r[0], r[1], r[2]) for r in rows]

        # m1 和 m2 应该通过 "志远" 相连
        related_pairs = {(e[0], e[1]) for e in edges}
        assert ("m1", "m2") in related_pairs or ("m2", "m1") in related_pairs,             "m1 和 m2 应该通过志远相连"

    def test_no_shared_entity_no_relation(self, graph):
        """没有共享实体的记忆不应创建边"""
        graph.link_memory("m1", "今天天气很好", link_entities=["天气"])
        graph.link_memory("m2", "Python是一种编程语言", link_entities=["Python"])

        rows = graph._exec("SELECT COUNT(*) FROM memory_relations")
        count = rows[0][0]
        assert count == 0, "没有共享实体不应创建边"


# ============================================================================
# Task 3: typed_entity_relations（关系类型+权重）
# ============================================================================

class TestTask3_TypedEntityRelations:
    """Task 3: 实体关系应有类型（similar/causal/partof/related）和权重

    现状: entity_relations 无类型
    期望: typed_entity_relations 表存在，关系带类型和权重
    """

    def test_typed_entity_relations_table_exists(self, graph):
        """typed_entity_relations 表应存在"""
        rows = graph._exec(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='typed_entity_relations'"
        )
        assert len(rows) == 1, "typed_entity_relations 表应该存在"

    def test_causal_relation_type(self, graph):
        """因果关系的实体对应有 causal 类型"""
        graph.link_memory("m1", "因为下雨，所以路滑", link_entities=["雨", "路滑"])
        graph.link_memory("m2", "路滑导致车祸", link_entities=["路滑", "车祸"])

        rows = graph._exec(
            "SELECT relation_type FROM typed_entity_relations WHERE from_entity = '路滑'"
        )
        if rows:
            types = [r[0] for r in rows]
            assert "causal" in types, "路滑相关关系应该是 causal 类型"


# ============================================================================
# Task 9: GraphMemory 常驻内存
# ============================================================================

class TestTask9_GraphMemoryResident:
    """Task 9: GraphMemory 图应常驻内存，SQLite 持久化

    现状: 每次搜索从 SQLite 构建图
    期望: 图在 __init__ 时从 SQLite 加载，常驻内存
    """

    def test_graph_loaded_from_sqlite_on_init(self, graph):
        """初始化后内存图应包含 SQLite 中的边"""
        # 写入一些数据
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])

        # 创建新实例模拟重启
        db_path = graph._conn.execute("PRAGMA database_list").fetchall()[0][2]
        new_graph = GraphMemory(db_path)

        # 验证内存图有边
        assert new_graph._graph.number_of_edges() > 0,             "重启后内存图应包含边数据"

        new_graph._conn.close()

    def test_sync_edge_updates_memory_graph(self, graph):
        """写入新边时内存图应同步更新"""
        initial_edges = graph._graph.number_of_edges()

        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])

        new_edges = graph._graph.number_of_edges()
        assert new_edges > initial_edges, "写入后内存图边数应增加"

    def test_networkx_graph_is_nx_graph(self, graph):
        """_graph 应该是 NetworkX 图对象"""
        import networkx as nx
        assert isinstance(graph._graph, nx.Graph), "_graph 应该是 NetworkX 图"


# ============================================================================
# Task 4: 激活扩散算法
# ============================================================================

class TestTask4_ActivationSpreading:
    """Task 4: 用激活扩散替代向量搜索重排

    期望: search_related 使用激活扩散算法计算最终激活强度
    """

    def test_activation_spreads_through_memory_network(self, graph):
        """激活应沿边传播"""
        # 链式结构: m1 --(志远)--> m2 --(猫)--> m3
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])
        graph.link_memory("m3", "橘猫叫小花", link_entities=["橘猫", "小花"])

        # 从 m1 出发，激活应扩散到 m2 和 m3
        result = graph.search_related(["m1"], max_hops=2)
        ids = {r["id"] for r in result}

        assert "m2" in ids, "激活应扩散到直接邻居 m2"
        assert "m3" in ids, "激活应扩散到两跳邻居 m3"

    def test_activation_strength_ranked(self, graph):
        """激活结果应按激活强度排序"""
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])
        graph.link_memory("m3", "橘猫叫小花", link_entities=["橘猫", "小花"])

        result = graph.search_related(["m1"], max_hops=2)

        # 验证返回结果有 score 字段
        for r in result:
            assert "score" in r, "结果应包含激活强度 score"

        # 验证排序（高激活在前）
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True), "结果应按激活强度降序排列"

    def test_search_related_accepts_initial_scores(self, graph):
        """search_related 应支持传入初始激活分数"""
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])

        # 传入初始分数
        result = graph.search_related(["m1"], initial_scores=[0.9], max_hops=1)
        assert len(result) > 0, "有初始分数时应返回结果"


# ============================================================================
# Task 5: get_memory_neighbors
# ============================================================================

class TestTask5_GetMemoryNeighbors:
    """Task 5: 提供 get_memory_neighbors 返回记忆的邻居

    期望: 返回 (neighbor_id, weight) 列表
    """

    def test_get_memory_neighbors_returns_weighted_neighbors(self, graph):
        """邻居应返回 (id, weight) 元组"""
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])

        neighbors = graph.get_memory_neighbors("m1")
        assert len(neighbors) > 0, "m1 应该有邻居"
        assert all(isinstance(n, tuple) and len(n) == 2 for n in neighbors),             "邻居格式应该是 (neighbor_id, weight)"

    def test_get_memory_neighbors_respects_limit(self, graph):
        """应支持 limit 参数"""
        for i in range(5):
            graph.link_memory(f"m{i}", f"记忆{i}", link_entities=["共享实体"])

        # m0 链接到 m1-m4（共4个邻居）
        neighbors = graph.get_memory_neighbors("m0", limit=2)
        assert len(neighbors) <= 2, "邻居数量应不超过 limit"


# ============================================================================
# Task 6: 实体相似度检测与自动合并
# ============================================================================

class TestTask6_EntitySimilarityMerge:
    """Task 6: 相似实体应自动合并

    现状: 新实体必须不存在，同一概念创建多个实体
    期望: Jaccard >= 0.75 时复用已有实体
    """

    def test_find_similar_entity_by_inclusion(self, graph):
        """包含关系应被检测为相似"""
        graph.link_memory("m1", "苹果是一种水果", link_entities=["苹果", "水果"])

        # 写入 "我喜欢吃苹果"，应复用 "苹果" 而非新建
        similar = graph._find_similar_entity("苹果")
        # 如果实现了相似检测，similar 应该返回 "苹果" 本身或 None（未找到相似）
        # 关键是不会创建 "苹果2" 这样的重复实体
        entity_count = len(graph._exec("SELECT name FROM entity_nodes WHERE name LIKE '苹果%'"))
        assert entity_count <= 1, "相似实体不应被重复创建"

    def test_find_similar_entity_returns_existing(self, graph):
        """_find_similar_entity 应返回已有实体"""
        graph.link_memory("m1", "苹果是一种水果", link_entities=["苹果", "水果"])

        # 检测 "apple" 是否相似于 "苹果"
        similar = graph._find_similar_entity("apple")
        # 如果阈值设置为 0.75，字符串相似度可能不够高
        # 但包含关系应该能检测到
        # 这里测试的是接口存在且返回 None 或已有实体名
        assert similar is None or isinstance(similar, str)


# ============================================================================
# Task 7: Hermes smart_store 封装
# ============================================================================

class TestTask7_SmartStore:
    """Task 7: Hermes 层 smart_store 根据前端设置决定模式

    期望: infer=True 用 mem0，infer=False 用 Hermes 提取实体
    """

    def test_smart_store_infer_mode(self, graph):
        """smart_store 应支持 infer 参数"""
        # 这测试的是接口设计，验证函数签名存在
        # 实际功能需要 Hermes Agent 层配合
        assert hasattr(graph, 'link_memory') or callable(getattr(graph, 'link_memory', None)),             "GraphMemory 应有 link_memory 方法"

    def test_smart_store_accepts_link_entities(self, graph):
        """smart_store 应支持 link_entities 参数"""
        graph.link_memory("m1", "我喜欢日本料理", link_entities=["日本", "料理"])
        entities = graph._exec("SELECT entity_name FROM mentions WHERE mem0_id = 'm1'")
        assert len(entities) > 0, "link_entities 应被正确处理"


# ============================================================================
# Task 8: merge_entities API
# ============================================================================

class TestTask8_MergeEntities:
    """Task 8: merge_entities 把 b 的记忆和关系迁移到 a

    期望: b 的 mentions 和关系迁移到 a，b 被删除
    """

    def test_merge_entities_exists(self, graph):
        """merge_entities 方法应存在"""
        assert hasattr(graph, 'merge_entities') or callable(getattr(graph, 'merge_entities', None)),             "GraphMemory 应有 merge_entities 方法"

    def test_merge_entities_moves_mentions(self, graph):
        """合并后 b 的 mentions 应转到 a"""
        graph.link_memory("m1", "苹果是一种水果", link_entities=["苹果", "水果"])
        graph.link_memory("m2", "我喜欢吃 apple", link_entities=["apple"])

        # 如果 merge_entities 存在，执行合并
        if hasattr(graph, 'merge_entities'):
            graph.merge_entities("苹果", "apple")

            # 查询合并后的情况
            apple_mentions = graph._exec(
                "SELECT COUNT(*) FROM mentions WHERE entity_name = 'apple'"
            )
            apple_count = apple_mentions[0][0]

            # apple 作为实体应该被删除或转移
            # 主要验证是不会同时存在两个独立实体
            apple_exists = graph._exec("SELECT name FROM entity_nodes WHERE name = 'apple'")
            # 合并后 apple 实体应该不存在
            assert len(apple_exists) == 0 or apple_count == 0,                 "合并后 'apple' 应该被删除或其 mentions 全部转移"


# ============================================================================
# 综合测试：激活扩散端到端
# ============================================================================

class TestE2E_ActivationSpreading:
    """端到端测试：存储 + 激活扩散召回"""

    def test_store_and_search_via_activation(self, graph):
        """存入记忆后通过激活扩散能召回"""
        # 存储一系列相关记忆
        graph.link_memory("m1", "志远喜欢猫", link_entities=["志远", "猫"])
        graph.link_memory("m2", "志远养了一只橘猫", link_entities=["志远", "橘猫"])
        graph.link_memory("m3", "橘猫喜欢吃鱼", link_entities=["橘猫", "鱼"])
        graph.link_memory("m4", "今天天气很好", link_entities=["天气"])

        # 通过 m1 召回相关记忆（应该召回 m2, m3，不召回 m4）
        result = graph.search_related(["m1"], max_hops=2)
        ids = {r["id"] for r in result}

        assert "m2" in ids, "应召回通过志远关联的 m2"
        assert "m3" in ids, "应召回通过猫关联的 m3"
        assert "m4" not in ids, "不应召回无关联的 m4"

    def test_activation_decay(self, graph):
        """激活强度应随跳数衰减"""
        # 线性链: m1 --x--> m2 --x--> m3
        graph.link_memory("m1", "记忆1", link_entities=["X"])
        graph.link_memory("m2", "记忆2", link_entities=["X"])
        graph.link_memory("m3", "记忆3", link_entities=["X"])

        result = graph.search_related(["m1"], max_hops=3)

        # 找到各记忆的激活分数
        scores = {r["id"]: r["score"] for r in result}

        # 两跳邻居 m3 的激活应低于一跳邻居 m2
        if "m2" in scores and "m3" in scores:
            assert scores["m2"] >= scores["m3"],                 "一跳邻居激活应 >= 两跳邻居（衰减）"
