"""程序记忆调度器（T007/T009）

周期性任务：后端明确定时任务或手动触发，不依赖 daemon 调度。

任务类型：
  1. mine: 从 brain_runs.jsonl 采集样本并提炼模板（低频）
  2. decay: 对长期不用的模板执行衰减
  3. archive: 将 deprecated 且长期不用的模板归档
  4. refresh_state: 刷新检查点的统计计数
"""

import logging
import threading
from typing import Optional

from main_brain.procedural_memory.collector import collect_procedure_examples
from main_brain.procedural_memory.miner import mine_procedure_templates
from main_brain.memory.procedural.store import get_procedure_store
from main_brain.memory.procedural.decay import apply_decay, check_archive, refresh_state_counts
from main_brain.procedural_memory.trace import (
    get_last_processed_run_id,
    set_last_processed_run_id,
    advance_example_seq,
    is_cooldown,
    set_cooldown,
    get_state_summary,
)

logger = logging.getLogger("main_brain.procedural.scheduler")


def run_mining(
    window: int = 50,
    *,
    min_support: int = 3,
    min_success_rate: float = 0.7,
    dry_run: bool = False,
) -> dict:
    """执行一次程序记忆提炼流水线。

    Args:
        window: 读取最近多少条运行记录。
        min_support: 聚类最少样本数。
        min_success_rate: 聚类最低成功率。
        dry_run: 预览模式，不写库。

    Returns:
        提炼结果摘要。
    """
    if not dry_run and is_cooldown():
        logger.info("[procedural.scheduler] in cooldown, skipping mine")
        return {"ok": False, "reason": "cooldown", "skipped": True}

    store = get_procedure_store()
    last_run_id = get_last_processed_run_id()

    # 1. 采集样本
    examples = collect_procedure_examples(
        window=window,
        modes=None,
        min_cycles=1,
        after_run_id=last_run_id,
    )
    if not examples:
        return {"ok": True, "examples": 0, "new_templates": 0, "reason": "no examples found"}

    # 2. 提炼模板
    existing_count = store.get_counts()["total_raw"]
    templates = mine_procedure_templates(
        examples,
        min_support=min_support,
        min_success_rate=min_success_rate,
        existing_count=existing_count,
    )
    if not templates:
        if not dry_run:
            existing_run_ids = {ex.run_id for ex in store.get_all_examples()}
            new_examples = [ex for ex in examples if ex.run_id not in existing_run_ids]
            if new_examples:
                store.append_examples(new_examples)
            set_last_processed_run_id(examples[-1].run_id)
            advance_example_seq(len(examples))
            set_cooldown(minutes=10)
        return {"ok": True, "examples": len(examples), "new_templates": 0, "reason": "no templates mined"}

    # 3. 写入
    if not dry_run:
        existing_run_ids = {ex.run_id for ex in store.get_all_examples()}
        new_examples = [ex for ex in examples if ex.run_id not in existing_run_ids]
        if new_examples:
            store.append_examples(new_examples)
        store.save_templates(templates)
        set_last_processed_run_id(examples[-1].run_id)
        advance_example_seq(len(examples))
        set_cooldown(minutes=10)

    logger.info(
        "[procedural.scheduler] mined %d templates from %d examples (dry_run=%s)",
        len(templates), len(examples), dry_run,
    )
    return {
        "ok": True,
        "examples": len(examples),
        "new_templates": len(templates),
        "templates": [t.template_id for t in templates] if dry_run else [],
        "dry_run": dry_run,
    }


def run_decay(dry_run: bool = False) -> dict:
    """执行衰减和归档。"""
    store = get_procedure_store()
    before = store.get_counts()

    if not dry_run:
        apply_decay(store)
        archived = check_archive(store)
        refresh_state_counts(store)
    else:
        archived = []

    after = store.get_counts()
    return {
        "ok": True,
        "dry_run": dry_run,
        "before": before,
        "after": after,
        "archived": archived,
    }


def dry_run_mining(window: int = 50, **kwargs) -> dict:
    """预览模式：采集+提炼但不写库。"""
    return run_mining(window=window, dry_run=True, **kwargs)


def get_module_state() -> dict:
    """返回程序记忆模块的完整状态摘要。"""
    store = get_procedure_store()
    state = store.get_state()
    counts = store.get_counts()
    templates = store.get_all_templates()

    active = [t.template_id for t in templates if t.status == "active"]
    proposed = [t.template_id for t in templates if t.status == "proposed"]
    cooling = [t.template_id for t in templates if t.status == "cooling"]
    deprecated = [t.template_id for t in templates if t.status == "deprecated"]
    draft = [t.template_id for t in templates if t.status == "draft"]

    return {
        "state": state.to_dict(),
        "counts": counts,
        "templates": {
            "active": active,
            "proposed": proposed,
            "cooling": cooling,
            "deprecated": deprecated,
            "draft": draft,
        },
    }
