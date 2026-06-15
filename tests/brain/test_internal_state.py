"""内部状态层 (Internal State System) 单元测试

覆盖 plan 第九章验收标准里全部数值逻辑：
  Concern cap / 衰减 / 不衰减存盘 / 删除条件
  Goal bias 区分优先级
  OpenLoop Jaccard merge / 创建规则
  Pending 双路径 / 无 content / 发送优先级
  Refractory 分类型 / 独立于 pending
  Working Set upsert
"""
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest


@pytest.fixture
def state(tmp_path, monkeypatch):
    """每个用例独立 internal_state.json + 全新单例。"""
    state_path = tmp_path / "internal_state.json"
    import backend.modules.brain.state.store as store
    monkeypatch.setattr(store, "_STATE_PATH", str(state_path))
    # 清掉所有 Manager / InternalState 单例，强制从新路径重建
    from backend.modules.brain.state import reset_singletons
    reset_singletons()
    yield state_path
    reset_singletons()


# ── Concern ───────────────────────────────────────────────

def test_base_activation_caps_at_1(state):
    from backend.modules.brain.state import get_concerns
    c = get_concerns()
    for _ in range(10):
        c.activate("海马体")  # 每次 +0.15
    assert c.get_base("海马体") == 1.0  # 不超 1.0


def test_effective_today_equals_base(state):
    from backend.modules.brain.state import get_concerns
    c = get_concerns()
    c.activate("意识流")
    assert c.get_effective("意识流") == pytest.approx(0.15)  # base×0.78^0


def test_effective_decay_3_days(state):
    from backend.modules.brain.state import get_concerns
    from backend.modules.brain.state import store
    c = get_concerns()
    for _ in range(7):
        c.activate("长期记忆")  # base=1.0
    # 手动把 last_activated 推到 3 天前
    with store.get_state().transaction() as data:
        for cc in data["concerns"]:
            if cc["node_id"] == "长期记忆":
                cc["last_activated"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    expected = round(1.0 * (0.78 ** 3), 4)
    assert c.get_effective("长期记忆") == pytest.approx(expected, abs=1e-4)


def test_base_not_decayed_on_disk(state):
    """重启（重新加载）后 base_activation 不变。"""
    from backend.modules.brain.state import get_concerns, reset_singletons
    from backend.modules.brain.state import store
    c = get_concerns()
    for _ in range(5):
        c.activate("联想")
    base_before = c.get_base("联想")
    # 模拟重启
    reset_singletons()
    assert get_concerns().get_base("联想") == base_before


def test_prune_keeps_recent_cold(state):
    """effective<0.05 但 <180 天 → 保留。"""
    from backend.modules.brain.state import get_concerns, store
    c = get_concerns()
    with store.get_state().transaction() as data:
        data["concerns"] = [{
            "node_id": "冷节点",
            "base_activation": 0.8,
            "last_activated": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        }]
    removed = c.prune()
    assert removed == 0
    assert c.get_base("冷节点") == 0.8  # 还在


def test_prune_removes_old_cold(state):
    """effective<0.05 且 >180 天 → 移除。"""
    from backend.modules.brain.state import get_concerns, store
    c = get_concerns()
    with store.get_state().transaction() as data:
        data["concerns"] = [{
            "node_id": "老节点",
            "base_activation": 0.8,
            "last_activated": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
        }]
    removed = c.prune()
    assert removed == 1
    assert c.get_base("老节点") == 0.0


def test_self_activate_tiny_boost(state):
    from backend.modules.brain.state import get_concerns
    c = get_concerns()
    for _ in range(50):
        c.self_activate("自激节点")  # 每次 +0.002
    assert c.get_base("自激节点") == pytest.approx(0.1, abs=1e-3)  # 50×0.002


def test_concern_bias_weight(state):
    """5 个实体各 effective 1.0 → (5×1.0)×0.005 = 0.025。"""
    from backend.modules.brain.state import get_concerns
    c = get_concerns()
    for n in ["e1", "e2", "e3", "e4", "e5"]:
        for _ in range(7):
            c.activate(n)  # base=1.0 → effective=1.0
    assert c.concern_bias_for_entities(["e1", "e2", "e3", "e4", "e5"]) == pytest.approx(0.025, abs=1e-4)


# ── Goals ─────────────────────────────────────────────────

def test_goal_bias_priority(state):
    """priority=0.95 → 0.0095；priority=0.3 → 0.003。"""
    from backend.modules.brain.state import get_goals, store
    with store.get_state().transaction() as data:
        data["goals"] = [
            {"name": "高优", "priority": 0.95, "related_concepts": ["情景记忆"]},
            {"name": "低优", "priority": 0.3, "related_concepts": ["完全无关"]},
        ]
    g = get_goals()
    assert g.goal_bias_for_entities(["情景记忆"]) == pytest.approx(0.0095, abs=1e-5)
    assert g.goal_bias_for_entities(["情景记忆"]) > g.goal_bias_for_entities(["完全无关"])


# ── Open Loops ────────────────────────────────────────────

def test_jaccard_no_merge_at_half(state):
    """[a,b] 与 [a,b,c,d] Jaccard=0.5，不 merge → 2 条。"""
    from backend.modules.brain.state import get_open_loops
    ol = get_open_loops()
    ol.create("为什么人会走神？", ["意识流", "注意力"])
    ol.create("为何意识总飘走？", ["意识流", "注意力", "认知", "海马体"])
    assert len(ol.get_open()) == 2


def test_jaccard_merge_identical(state):
    """完全重叠 Jaccard=1.0 → merge，thought_count+1。"""
    from backend.modules.brain.state import get_open_loops
    ol = get_open_loops()
    ol.create("为什么人会走神？", ["意识流", "注意力"])
    ol.create("为何人总走神？", ["意识流", "注意力"])
    loops = ol.get_open()
    assert len(loops) == 1
    assert loops[0]["thought_count"] == 2


def test_open_loop_rejects_non_question(state):
    from backend.modules.brain.state import get_open_loops
    ol = get_open_loops()
    # 非问句 → 拒绝（即使有 2 节点）
    assert ol.create("今天天气不错", ["意识流", "注意力"]) is None
    assert len(ol.get_open()) == 0


def test_open_loop_accepts_question_with_2_nodes(state):
    from backend.modules.brain.state import get_open_loops
    ol = get_open_loops()
    # 问句 + ≥2 节点 → 接受（无需 concept 检查，graph 无关）
    loop = ol.create("为什么人会走神？", ["意识流", "注意力"])
    assert loop is not None
    assert len(ol.get_open()) == 1


# ── Refractory ────────────────────────────────────────────

def test_refractory_type_separation(state):
    """recent_interest 冷却不阻断 open_loop 表达。"""
    from backend.modules.brain.state import get_expression_history
    eh = get_expression_history()
    eh.record("interest", "海马体")
    assert eh.is_in_refractory("interest", "海马体") is True
    assert eh.is_in_refractory("open_loop", "海马体") is False


def test_refractory_independent_of_pending(state):
    """删除 pending 后冷却仍在。"""
    from backend.modules.brain.state import get_expression_history, get_pending, store
    eh = get_expression_history()
    p = get_pending()
    p._create("recent_interest", "海马体", 0.5, "concern")
    # 标记表达会记录 refractory
    pendings = store.get_state().snapshot()["pending_expressions"]
    p.mark_expressed(pendings[0]["id"])
    # 删掉 pending
    with store.get_state().transaction() as data:
        data["pending_expressions"] = []
    # 冷却仍在
    assert eh.is_in_refractory("interest", "海马体") is True


# ── Working Set ───────────────────────────────────────────

def test_working_set_upsert_no_dup(state):
    from backend.modules.brain.state import get_working_set
    ws = get_working_set()
    ws.upsert("node", "海马体", 0.5)
    ws.upsert("node", "海马体", 0.3)  # score=max(0.5,0.3)=0.5，不新增
    active = ws.get_active()
    assert len([w for w in active if w["ref_id"] == "海马体"]) == 1
    assert active[0]["score"] == 0.5


# ── Pending Expression ────────────────────────────────────

def test_pending_stores_no_content(state):
    """pending 只存 source_node_id + expression_score，不存 content。"""
    from backend.modules.brain.state import get_pending
    p = get_pending()
    p._create("recent_interest", "海马体", 0.7, "concern")
    entry = p.get_unexpressed()[0]
    assert "content" not in entry
    assert entry["source_node_id"] == "海马体"
    assert entry["expression_score"] == 0.7


def test_send_priority_highest_score(state):
    """多条 pending → 发 expression_score 最高的。"""
    from backend.modules.brain.state import get_pending
    p = get_pending()
    p._create("recent_interest", "低分", 0.2, "concern")
    p._create("recent_interest", "高分", 0.9, "concern")
    pick = p.pick_to_send()
    assert pick is not None
    assert pick["source_node_id"] == "高分"


def test_evaluate_and_generate_threshold(state):
    """concern 达标 → 生成 pending。"""
    from backend.modules.brain.state import get_concerns, get_pending
    c = get_concerns()
    for _ in range(7):
        c.activate("热点")  # base=1.0, drive≈0.8 → recent≈0.8 > 0.15
    n = get_pending().evaluate_and_generate()
    assert n >= 1
