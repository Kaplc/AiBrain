"""Drives — 驱动力（固定值，代表人格，不衰减）

固定值：curiosity(0.8) / companionship(0.9) / self_expression(0.7) / completion(0.6)
存在 internal_state.json 里便于可视化和未来微调，但语义上是只读常量。

NodeType → Drive 映射（决策 #12，见 plan 模块 0.5）：
  person/user      → companionship
  self             → self_expression
  concept/project/emotion/goal/rule/exp → curiosity（默认）
  open_loop（非实体类型，pending 来源）→ completion

Drive 在 pending 表达时调制：expression_score = effective × drive_weight。
"""
import logging

from .store import get_state

logger = logging.getLogger('state.drives')

# NodeType → drive 名映射（实体类型来自 entity_extract / graph 默认实体）
NODE_TYPE_TO_DRIVE = {
    "person": "companionship",
    "user": "companionship",
    "self": "self_expression",
    # 其余类型（concept/project/emotion/goal/rule/exp）落到默认 curiosity
}
DEFAULT_DRIVE = "curiosity"
DRIVE_FOR_OPEN_LOOP = "completion"


class DriveManager:
    """驱动力管理器（只读）。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    def get_all(self) -> dict[str, float]:
        """{drive_name: value} 全量。"""
        drives = self._state.snapshot().get("drives", {})
        # 补齐缺失的默认 drive 名，避免 KeyError
        for name in ("curiosity", "companionship", "self_expression", "completion"):
            drives.setdefault(name, 0.0)
        return drives

    def value(self, drive_name: str) -> float:
        return float(self.get_all().get(drive_name, 0.0))

    def drive_name_for_node_type(self, node_type: str) -> str:
        return NODE_TYPE_TO_DRIVE.get(node_type, DEFAULT_DRIVE)

    def drive_for_node(self, node_id: str) -> float:
        """查节点的 entity 类型 → 对应 drive 值。图不可用回落 curiosity。"""
        try:
            from main_brain.memory.graph import get_graph
            g = get_graph()
            if g is not None:
                rows = g._exec("SELECT type FROM entity_nodes WHERE name = ?", (node_id,))
                if rows:
                    drive_name = self.drive_name_for_node_type(rows[0][0])
                    return self.value(drive_name)
        except Exception as e:
            logger.warning(f"[drives] drive_for_node failed for {node_id!r}: {e}")
        return self.value(DEFAULT_DRIVE)

    def drive_for_open_loop(self) -> float:
        """OpenLoop 来源用 completion 驱动。"""
        return self.value(DRIVE_FOR_OPEN_LOOP)
