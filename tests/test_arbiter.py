"""Arbiter 仲裁层测试（T015 / FR-014-r2）

覆盖：
  - ActivitySelector 返回 3-tuple (activity, reason, confidence)
  - compute_arbiter_confidence 阈值计算
  - Arbiter mock 解析
  - Novelty 追踪
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'modules'))
os.environ['BRAIN_CONFIG_PATH'] = os.path.join(
    os.path.dirname(__file__), '..', 'backend', 'main_brain', 'data', 'config.json',
)

from main_brain.activities.registry import ensure_loaded
ensure_loaded()


def test_selector_returns_3tuple():
    """ActivitySelector.select() 返回 (activity, reason, confidence)。"""
    from main_brain.activity_selector import get_activity_selector
    sel = get_activity_selector()

    # short_tick -> wait, 1.0
    act, reason, conf = sel.select(
        {'idle_seconds': 0, 'energy': 0.5, 'pending_expressions': []},
        'short_tick',
    )
    assert act == 'wait', f'expected wait, got {act}'
    assert conf == 1.0, f'expected 1.0, got {conf}'
    print(f'  [OK] short_tick -> {act} conf={conf}')

    # long_tick -> organize_memory
    act, reason, conf = sel.select(
        {'idle_seconds': 0, 'energy': 0.6, 'pending_expressions': []},
        'long_tick',
    )
    assert act == 'organize_memory'
    assert conf == 0.75
    print(f'  [OK] long_tick -> {act} conf={conf}')

    # daily_tick -> reflect, 0.90
    act, reason, conf = sel.select(
        {'idle_seconds': 0, 'energy': 0.5, 'pending_expressions': []},
        'daily_tick',
    )
    assert act == 'reflect' and conf == 0.90
    print(f'  [OK] daily_tick -> {act} conf={conf}')

    # observe mode -> wait, 1.0
    act, reason, conf = sel.select({}, 'medium_tick', autonomy_level='observe')
    assert act == 'wait' and conf == 1.0
    print(f'  [OK] observe -> {act} conf={conf}')


def test_arbiter_threshold():
    """compute_arbiter_confidence 阈值判定。"""
    from main_brain.arbiter import compute_arbiter_confidence, needs_arbitration

    life_idle = {
        'idle_seconds': 800, 'energy': 0.7, 'open_loops': [],
        'pending_expressions': [{'text': 'hi'}],
    }

    # wait -> 低置信，需要仲裁
    conf = compute_arbiter_confidence(('wait', 'nothing'), 'medium_tick', life_idle)
    assert conf < 0.55, f'wait should be low confidence, got {conf}'
    assert needs_arbitration(conf)
    print(f'  [OK] wait conf={conf} -> needs_arbitration')

    # proactive_contact -> 高置信
    conf = compute_arbiter_confidence(
        ('proactive_contact', 'idle enough'), 'medium_tick', life_idle,
    )
    assert conf >= 0.55, f'proactive should be high confidence, got {conf}'
    assert not needs_arbitration(conf)
    print(f'  [OK] proactive conf={conf} -> no arbitration')

    # daily reflect -> 极高置信
    conf = compute_arbiter_confidence(('reflect', 'daily'), 'daily_tick', {})
    assert conf == 0.90
    print(f'  [OK] daily reflect conf={conf}')


def test_arbiter_mock():
    """Arbiter.arbitrate() mock 响应解析。"""
    from main_brain.arbiter import get_arbiter

    arb = get_arbiter()
    mock = '{"activity": "reflect", "reason": "needs reflection", "confidence": 0.8}'
    act, reason, conf = arb.arbitrate({}, 'medium_tick', mock_response=mock)
    assert act == 'reflect', f'expected reflect, got {act}'
    assert conf == 0.8, f'expected 0.8, got {conf}'
    print(f'  [OK] arbiter mock -> {act} conf={conf}')

    # invalid JSON -> fallback
    act, reason, conf = arb.arbitrate(
        {}, 'medium_tick', mock_response='not json',
        fallback=('wait', 'fallback'),
    )
    assert act == 'wait'
    print(f'  [OK] arbiter invalid json -> fallback to wait')


def test_novelty_tracking():
    """Arbiter 记录最近活动供 novelty 检测。"""
    from main_brain.arbiter import get_arbiter

    arb = get_arbiter()
    arb.record_activity('medium_tick', 'self_learn')
    arb.record_activity('medium_tick', 'self_learn')
    arb.record_activity('medium_tick', 'self_learn')
    assert arb.get_repeat_count('medium_tick', 'self_learn') == 3
    print(f'  [OK] novelty: self_learn repeated 3 times')

    # 换活动后重复计数重置
    arb.record_activity('medium_tick', 'reflect')
    assert arb.get_repeat_count('medium_tick', 'self_learn') == 0
    print(f'  [OK] novelty: after reflect, self_learn count reset')


if __name__ == '__main__':
    test_selector_returns_3tuple()
    test_arbiter_threshold()
    test_arbiter_mock()
    test_novelty_tracking()
    print()
    print('ALL ARBITER TESTS PASSED')
