"""Output Adapter（T003）— 读取 output.json 增量 + 可选 brain run 摘要

只负责把 output.json 的工作记忆读取能力包装给沉淀 orchestrator，不复制 workmemory
单例。读取失败降级返回空（不阻断沉淀流程）。

外部访问：
    from main_brain.adapters.output import get_output_adapter
    get_output_adapter().read_recent(window_size)
"""
from __future__ import annotations

import logging

logger = logging.getLogger("main_brain.adapter.output")


class OutputAdapter:
    """output.json 读取 adapter（薄包装 WorkMemoryManager）。"""

    def read_all(self) -> list[dict]:
        """读取 output.json 全部条目（原始 dict）。失败返回 []。"""
        try:
            from main_brain.memory.workmemory import get_work_memory
            return get_work_memory().output_mem_read()
        except Exception as e:
            logger.warning(f"[output_adapter] read output.json failed: {e}")
            return []

    def read_recent(self, window_size: int = 20) -> list[dict]:
        """读取最近 window_size 条（按 seq 升序）。"""
        entries = self.read_all()
        if not entries:
            return []
        entries.sort(key=lambda e: int(e.get("seq", 0) or 0))
        return entries[-window_size:]

    def read_incremental(self, last_seq: int, window_size: int = 20) -> list[dict]:
        """读取 seq > last_seq 的增量条目（升序，最多 window_size 条）。"""
        entries = self.read_all()
        if not entries:
            return []
        inc = [e for e in entries
               if isinstance(e, dict) and int(e.get("seq", 0) or 0) > last_seq]
        inc.sort(key=lambda e: int(e.get("seq", 0) or 0))
        return inc[:window_size]

    def max_seq(self) -> int:
        """当前 output.json 的最大 seq（无数据返回 0）。"""
        entries = self.read_all()
        if not entries:
            return 0
        return max((int(e.get("seq", 0) or 0) for e in entries if isinstance(e, dict)),
                   default=0)


_output_adapter: OutputAdapter | None = None


def get_output_adapter() -> OutputAdapter:
    global _output_adapter
    if _output_adapter is None:
        _output_adapter = OutputAdapter()
    return _output_adapter
