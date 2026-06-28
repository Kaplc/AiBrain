"""程序记忆与习惯模板系统

从 brain_runs.jsonl 中采集成功运行样本，提炼为可复用的动作模板，
在相似上下文中提供决策参考，并根据实际结果持续学习。
"""

from main_brain.procedural_memory.contracts import (
    ProcedureTemplate,
    ProcedureExample,
    ProcedureMatch,
    ProcedureFeedback,
    ProcedureState,
    TEMPLATE_STATUS,
    RISK_LEVELS,
    OUTCOMES,
)

# re-export auto_skill 公共符号（方便外部只从 procedural_memory 一级入口导入）
try:
    from main_brain.auto_skill import sync_all as _sync_all, list_deployed as _list_deployed
    sync_all = _sync_all
    list_deployed = _list_deployed
except ImportError:
    def sync_all() -> dict: return {"deployed": [], "removed": [], "errors": []}
    def list_deployed() -> list: return []
