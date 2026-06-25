"""Tool Adapter（T016）— 包装现有 ToolRegistry，白名单只读调用。

第一版只接白名单工具（plan FR-005），默认只放 memory_search 这类只读工具。
白名单来自 brain.json['tool_whitelist']，为空则 use_tool 安全降级（不执行）。
"""
from __future__ import annotations

import logging

from ..contracts import BrainJudgeDecision, BrainRunContext

logger = logging.getLogger("main_brain.adapter.tools")

# 默认白名单：只读、无副作用的安全工具
DEFAULT_WHITELIST = ["memory_search", "web_fetch"]


class ToolAdapter:
    """白名单工具调用 adapter。"""

    def _whitelist(self) -> list[str]:
        from ..config import get_brain_config
        wl = get_brain_config().get("tool_whitelist")
        if isinstance(wl, list) and wl:
            return [str(x) for x in wl]
        return list(DEFAULT_WHITELIST)

    def available_tools(self) -> list[dict]:
        """返回白名单内已注册工具的 {name, description}（供 judge/tool_context）。"""
        try:
            from modules.LLM.tools import get_tool_registry
            reg = get_tool_registry()
            wl = set(self._whitelist())
            return [
                {"name": t.name, "description": t.description[:80]}
                for t in reg.get_all_tools() if t.name in wl
            ]
        except Exception as e:
            logger.warning(f"[tool_adapter] list tools failed: {e}")
            return []

    def call(self, name: str, args: dict) -> str:
        """调用白名单内工具，返回结果字符串。非白名单返回拒绝。"""
        if name not in self._whitelist():
            return f"Error: tool {name!r} not in whitelist"
        try:
            from modules.LLM.tools import get_tool_registry
            return get_tool_registry().execute(name, args or {})
        except Exception as e:
            logger.warning(f"[tool_adapter] call {name} failed: {e}")
            return f"Error: {e}"

    # ── action_handler 约定 ─────────────────────────────────
    def handle_use_tool(self, decision: BrainJudgeDecision, ctx: BrainRunContext,
                        dry_run: bool) -> dict:
        args = decision.action_args or {}
        name = str(args.get("name", "")).strip()
        tool_args = args.get("args", {}) if isinstance(args.get("args"), dict) else {}
        if dry_run:
            return {"result_summary": f"[dry_run] use_tool: {name}"}
        if not name:
            return {"result_summary": "use_tool: 缺工具名"}
        result = self.call(name, tool_args)
        return {
            "result_summary": f"工具 {name}: {result[:120]}",
            "tool_results": [{"name": name, "result": result[:500], "args": tool_args}],
        }


_tool_adapter: ToolAdapter | None = None


def get_tool_adapter() -> ToolAdapter:
    global _tool_adapter
    if _tool_adapter is None:
        _tool_adapter = ToolAdapter()
    return _tool_adapter
