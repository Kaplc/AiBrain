"""Self Model — 轻量身份信息（回答「我是谁」）

最小集：name / traits / relationship。不含 life_story / chapter / milestone
（那些属于自我叙事层，V2 再说）。供 prompt 注入一个稳定的自我锚点。
"""
import logging

from .store import get_state

logger = logging.getLogger('state.self_model')


class SelfModelManager:
    """自我模型管理器（只读；V2 扩展 likes/dislikes/speaking_style/values）。"""

    def __init__(self, state=None):
        self._state = state or get_state()

    def get(self) -> dict:
        return self._state.snapshot().get("self_model", {})

    def name(self) -> str:
        return self.get().get("name", "猫猫")

    def traits(self) -> list[str]:
        return self.get().get("traits", [])

    def relationship(self) -> dict:
        return self.get().get("relationship", {})

    def summary(self) -> str:
        """供 prompt 注入的自我摘要文本。"""
        m = self.get()
        name = m.get("name", "猫猫")
        traits = m.get("traits", [])
        rel = m.get("relationship", {})
        parts = [f"我是{name}。"]
        if traits:
            parts.append(f"性格：{'、'.join(traits)}。")
        if rel:
            pairs = "、".join(f"{k}是我的{v}" for k, v in rel.items())
            parts.append(pairs + "。")
        return "".join(parts)
