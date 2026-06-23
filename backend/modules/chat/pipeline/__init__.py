"""
PromptPipeline — prompt 构造流水线
按配置顺序执行各个 Section，产出结构化 PromptComposition（稳定块 + 动态块）

用法：
    from .pipeline import PromptPipeline
    ctx = PromptContext(...)
    pipeline = PromptPipeline.get_instance()
    composition = pipeline.build(ctx)   # -> PromptComposition
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .context import PromptContext
from .composition import PromptComposition

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
        # 幂等：已注册则只更新定义，不重复追加到 _order。
        # 否则 init_pipeline() 每调一次都会让 section 翻倍，build() 会产出重复块。
        if section.name in self._sections:
            self._sections[section.name] = section
            return
        self._sections[section.name] = section
        self._order.append(section.name)

    def set_order(self, names: list[str]) -> None:
        self._order = names

    def get_order(self) -> list[str]:
        return list(self._order)

    def build(self, ctx: PromptContext) -> PromptComposition:
        """按顺序执行所有启用的 Section，返回结构化 PromptComposition

        各 Section 通过 ctx.add_stable / ctx.add_block 产出独立块；
        非必需 Section 失败记 warning 并跳过，必需 Section 失败直接抛错。
        """
        # 自愈：_preload 后台线程还没跑到 init_pipeline（或那次失败了）时，
        # 流水线可能为空。这里懒加载一次，保证稳定前缀始终在场，
        # 不依赖外部 ready_state 门禁。
        if not self._order:
            try:
                init_pipeline()
            except Exception as e:
                logger.warning(f"[prompt] lazy init_pipeline failed: {e}")

        ctx.stable_blocks.clear()
        ctx.dynamic_blocks.clear()
        ctx._order_counter = 0
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

        composition = PromptComposition()
        composition.stable_blocks = list(ctx.stable_blocks)
        composition.dynamic_blocks = list(ctx.dynamic_blocks)
        composition.metadata = dict(ctx.metadata)
        return composition


def init_pipeline() -> PromptPipeline:
    """注册所有 Section 并返回 Pipeline 实例"""
    pipeline = PromptPipeline.get_instance()
    from .sections import get_all_sections
    for sec in get_all_sections():
        pipeline.register(sec)
    logger.info(f"[prompt] pipeline initialized: {pipeline.get_order()}")
    return pipeline
