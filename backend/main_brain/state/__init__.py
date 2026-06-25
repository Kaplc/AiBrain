"""内部状态层 (Internal State System) — 猫猫的持续关注与主动表达

九层链路：Self → Drives → Goals → Concerns → WorkingSet → OpenLoops
              → PendingExpression → Refractory → Send

独立于记忆层，放在 main_brain/state/。所有 Manager 共享同一份
~/.aibrain/data/internal_state.json（经 InternalState 单例 + 锁原子读写）。

外部统一经模块转发访问：
    from main_brain.state import get_concerns, get_pending
    get_concerns().activate("海马体")
    get_pending().evaluate_and_generate()
"""
import logging

from .store import get_state, InternalState

logger = logging.getLogger('state')

# ── 各 Manager 单例缓存（共享同一个 InternalState）──────────
_self_model = None
_drives = None
_goals = None
_concerns = None
_open_loops = None
_working_set = None
_expression_history = None
_pending = None


def get_self_model():
    global _self_model
    if _self_model is None:
        from .self_model import SelfModelManager
        _self_model = SelfModelManager(get_state())
    return _self_model


def get_drives():
    global _drives
    if _drives is None:
        from .drives import DriveManager
        _drives = DriveManager(get_state())
    return _drives


def get_goals():
    global _goals
    if _goals is None:
        from .goals import GoalManager
        _goals = GoalManager(get_state())
    return _goals


def get_concerns():
    global _concerns
    if _concerns is None:
        from .concerns import ConcernManager
        _concerns = ConcernManager(get_state())
    return _concerns


def get_open_loops():
    global _open_loops
    if _open_loops is None:
        from .open_loops import OpenLoopManager
        _open_loops = OpenLoopManager(get_state())
    return _open_loops


def get_working_set():
    global _working_set
    if _working_set is None:
        from .working_set import WorkingSetManager
        _working_set = WorkingSetManager(get_state())
    return _working_set


def get_expression_history():
    global _expression_history
    if _expression_history is None:
        from .expression_history import ExpressionHistoryManager
        _expression_history = ExpressionHistoryManager(get_state())
    return _expression_history


def get_pending():
    global _pending
    if _pending is None:
        from .pending_expression import PendingExpressionManager
        _pending = PendingExpressionManager(get_state())
    return _pending


def reset_singletons():
    """测试用：清掉所有 Manager 单例（不删磁盘文件）。"""
    global _self_model, _drives, _goals, _concerns, _open_loops, _working_set, _expression_history, _pending
    for name in ("_self_model", "_drives", "_goals", "_concerns", "_open_loops",
                 "_working_set", "_expression_history", "_pending"):
        globals()[name] = None
    InternalState.reset_instance()


__all__ = [
    "get_state",
    "get_self_model",
    "get_drives",
    "get_goals",
    "get_concerns",
    "get_open_loops",
    "get_working_set",
    "get_expression_history",
    "get_pending",
    "reset_singletons",
]
