"""内部状态层存储骨干 — internal_state.json 单例加载/保存

九层状态（Self/Drives/Goals/Concerns/WorkingSet/OpenLoops/Pending/Refractory）
共享同一份 ~/.aibrain/data/internal_state.json。InternalState 单例持有内存 dict
+ 一把锁；各 Manager（concerns/open_loops/...）通过 transaction() 上下文做
原子「读改写」，成功才落盘，异常自动回滚到磁盘状态。

内部状态层 ≠ 记忆层，故独立放在 modules/brain/state/ 下，不挂 memory/。
外部访问统一经模块转发：
    from modules.brain.state import get_state, get_concerns
    get_concerns().activate("海马体")

节点身份约定：本系统里 node_id == entity_nodes.name（图的实体名主键）。
所以 Concern/OpenLoop 绑定的 node_id 就是实体名字符串，resolve_name_to_node_id
负责向 entity_nodes 校验该名字是否真实存在。
"""
import copy
import json
import logging
import os
import threading
from contextlib import contextmanager

logger = logging.getLogger('state')

_STATE_PATH = os.path.join(
    os.path.expanduser("~"), ".aibrain", "data", "internal_state.json"
)
CURRENT_VERSION = 5

# ── 默认状态模板 ──────────────────────────────────────────
_DEFAULT_STATE = {
    "version": CURRENT_VERSION,
    "self_model": {
        "name": "猫猫",
        "traits": ["好奇", "喜欢研究记忆", "喜欢联想"],
        "relationship": {"志远": "伙伴"},
    },
    "drives": {
        "curiosity": 0.8,
        "companionship": 0.9,
        "self_expression": 0.7,
        "completion": 0.6,
    },
    "goals": [
        {
            "name": "构建更接近人类的记忆系统",
            "priority": 0.95,
            "related_concepts": ["长期记忆", "情景记忆", "联想", "意识流", "entity_relations"],
            "created_at": "2026-06-10",
        }
    ],
    "concerns": [],
    "open_loops": [],
    "working_set": [],
    "pending_expressions": [],
    "expression_history": [],
}


def _load_or_init() -> dict:
    """加载 internal_state.json；缺失/损坏则返回默认模板的深拷贝。

    迁移：补齐所有顶层键，version<5 时丢弃旧版 pending_expressions（旧 schema
    含 content/importance，与新版 source_node_id/expression_score 不兼容）。
    """
    try:
        if os.path.exists(_STATE_PATH):
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("state root not object")
        else:
            data = {}
    except Exception as e:
        logger.warning(f"[state] load failed, using defaults: {e}")
        return copy.deepcopy(_DEFAULT_STATE)

    version = data.get("version", 0)
    # 补齐所有顶层键（缺失的用默认值，不覆盖已有）
    for key, default_val in _DEFAULT_STATE.items():
        if key == "version":
            continue
        if key not in data:
            data[key] = copy.deepcopy(default_val)

    # v5 迁移：清理旧 schema 的 pending_expressions（无 source_node_id 的条目）
    if version < CURRENT_VERSION:
        pe = data.get("pending_expressions", [])
        before = len(pe)
        data["pending_expressions"] = [
            p for p in pe if isinstance(p, dict) and p.get("source_node_id")
        ]
        if len(data["pending_expressions"]) != before:
            logger.info(
                f"[state] migrate pending_expressions: {before} -> "
                f"{len(data['pending_expressions'])} (dropped legacy)"
            )

    data["version"] = CURRENT_VERSION
    return data


def _save(data: dict) -> None:
    """原子落盘（写临时文件再替换，避免半写损坏）。"""
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATE_PATH)


class InternalState:
    """单例：内存 dict + 锁 + 原子持久化。

    所有 Manager 持有同一个 InternalState 实例，写操作用 transaction() 包裹，
    在锁内改内存 dict、成功落盘、异常回滚。读操作用 snapshot() 拿当前引用。
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._data = _load_or_init()
        self.lock = threading.RLock()  # 可重入，允许 Manager 内部组合调用

    @classmethod
    def get_instance(cls) -> "InternalState":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """测试用：清掉单例。"""
        with cls._instance_lock:
            cls._instance = None

    @contextmanager
    def transaction(self):
        """加锁执行读改写，正常退出落盘；异常回滚到磁盘状态再抛出。"""
        with self.lock:
            try:
                yield self._data
            except Exception:
                try:
                    self._data = _load_or_init()
                except Exception as e:
                    logger.warning(f"[state] rollback reload failed: {e}")
                raise
            else:
                try:
                    _save(self._data)
                except Exception as e:
                    logger.warning(f"[state] save failed (in-memory intact): {e}")

    def snapshot(self) -> dict:
        """只读快照（返回顶层 dict 引用，调用方不应修改）。"""
        return self._data

    def reload(self):
        """强制从磁盘重新加载。"""
        with self.lock:
            self._data = _load_or_init()


def get_state() -> InternalState:
    """获取 InternalState 单例。"""
    return InternalState.get_instance()
