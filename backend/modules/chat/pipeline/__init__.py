"""
PromptPipeline — prompt 构造流水线
按配置顺序执行各个 Section，拼接为完整 system prompt

用法：
    from .pipeline import PromptPipeline
    ctx = PromptContext(...)
    pipeline = PromptPipeline.get_instance()
    system_prompt = pipeline.run(ctx)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .context import PromptContext

logger = logging.getLogger('chat.pipeline')


@dataclass
class SectionDef:
    """prompt 片段定义"""
    name: str
    description: str
    execute: Callable
    enabled: bool = True
    required: bool = False


class PromptPipeline:
    """prompt 构造流水线单例"""

    _instance: Optional['PromptPipeline'] = None

    def __init__(self):
        self._sections: dict[str, SectionDef] = {}
        self._order: list[str] = []

    @classmethod
    def get_instance(cls) -> 'PromptPipeline':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, section: SectionDef) -> None:
        self._sections[section.name] = section
        self._order.append(section.name)

    def set_order(self, names: list[str]) -> None:
        self._order = names

    def get_order(self) -> list[str]:
        return list(self._order)

    def run(self, ctx: PromptContext) -> str:
        """按顺序执行所有启用的 Section，返回拼接后的 prompt"""
        ctx.parts.clear()
        for name in self._order:
            sec = self._sections.get(name)
            if sec is None or not sec.enabled:
                continue
            try:
                sec.execute(ctx)
            except Exception as e:
                logger.warning(f"[prompt] section '{name}' failed: {e}")
                if sec.required:
                    raise
        return ctx.build()


def init_pipeline() -> PromptPipeline:
    """注册所有 Section 并返回 Pipeline 实例"""
    pipeline = PromptPipeline.get_instance()
    from .sections import get_all_sections
    for sec in get_all_sections():
        pipeline.register(sec)
    logger.info(f"[prompt] pipeline initialized: {pipeline.get_order()}")
    return pipeline
