"""程序记忆检查点管理

通过 ProcedureStore 的 state 字段追踪处理进度，避免重复处理同一批运行数据。
"""

import logging
from main_brain.memory.procedural.store import get_procedure_store

logger = logging.getLogger("main_brain.procedural.trace")


def get_last_processed_run_id() -> str:
    """最近一次处理的 brain_run_id"""
    return get_procedure_store().get_state().last_mined_run_id


def set_last_processed_run_id(run_id: str):
    get_procedure_store().update_state(last_mined_run_id=run_id)
    logger.debug("[trace] checkpoint run_id=%s", run_id)


def get_last_example_seq() -> int:
    return get_procedure_store().get_state().last_example_seq


def set_last_example_seq(seq: int):
    get_procedure_store().update_state(last_example_seq=seq)
    logger.debug("[trace] checkpoint example_seq=%d", seq)


def advance_example_seq(n: int = 1):
    store = get_procedure_store()
    store.update_state(last_example_seq=store.get_state().last_example_seq + n)


def set_policy_version(version: str):
    get_procedure_store().update_state(policy_version=version)
    logger.info("[trace] policy_version=%s", version)


def is_cooldown() -> bool:
    """检查是否在全局冷却期"""
    state = get_procedure_store().get_state()
    if not state.cooldown_until:
        return False
    import datetime
    try:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        until = datetime.datetime.fromisoformat(
            state.cooldown_until.replace("Z", "+00:00")
        ).replace(tzinfo=None)
        chilled = now < until
        if chilled:
            logger.debug("[trace] cooldown active until %s", state.cooldown_until)
        return chilled
    except (ValueError, TypeError) as e:
        logger.warning("[trace] is_cooldown parse error: %s", e)
        return False


def set_cooldown(minutes: int = 30):
    """设置全局冷却"""
    import datetime
    until = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes))
    until_str = until.strftime("%Y-%m-%dT%H:%M:%SZ")
    get_procedure_store().update_state(cooldown_until=until_str)
    logger.info("[trace] cooldown set for %d min until %s", minutes, until_str)


def get_state_summary() -> dict:
    """返回给调试接口的检查点摘要"""
    store = get_procedure_store()
    state = store.get_state()
    counts = store.get_counts()
    return {
        **state.to_dict(),
        **counts,
    }
