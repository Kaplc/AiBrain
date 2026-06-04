"""
EventExtract Step - 后台异步事件提取
启动后台线程后立即返回，引擎不等待

读取 ctx.intermediate:
  - mem0_ids: 记忆 ID 列表
  - mem_texts: 记忆文本列表

不写入 intermediate（后台线程独立执行）
"""
import logging
import threading

logger = logging.getLogger('memory.pipeline')


def execute(ctx) -> None:
    """执行 EventExtract 步骤：后台线程提取事件

    Args:
        ctx: PipelineContext
    """
    meta = ctx.metadata or {}
    use_infer = meta.get("infer", True)
    if not use_infer:
        logger.info("[step:event_extract] infer=false, skip")
        return

    events = ctx.metadata.get("_events", [])
    if not events:
        logger.info("[step:event_extract] no events to process")
        return

    # 仅处理 ADD 事件
    add_events = [e for e in events if e.get("event") == "ADD" and e.get("id")]
    if not add_events:
        logger.info("[step:event_extract] no ADD events")
        return

    original_text = ctx.input_data

    def _bg_extract(events_list, orig_text):
        """后台线程：提取事件并推断事件链"""
        logger.info(f"[step:event_extract] background thread started | {len(events_list)} events")
        try:
            from modules.brain.memory.events import get_event_store
            es = get_event_store()
            if not es:
                logger.warning("[step:event_extract] EventStore not available, skip")
                return
            for ev in events_list:
                try:
                    logger.info(f"[step:event_extract] extracting events for {ev['id'][:8]}")
                    new_ids = es.extract_events_from_memory(ev["id"], ev.get("memory", ""))
                    if new_ids:
                        logger.info(f"[step:event_extract] extracted {len(new_ids)} events for {ev['id'][:8]}")
                        es.infer_event_chains(new_ids)
                    else:
                        logger.info(f"[step:event_extract] no events for {ev['id'][:8]} (concept/fact)")
                except Exception as e:
                    logger.warning(f"[step:event_extract] failed for {ev['id'][:8]}: {e}")
        except Exception as e:
            logger.warning(f"[step:event_extract] background thread error: {e}")
        logger.info("[step:event_extract] background thread done")

    # 启动后台线程
    threading.Thread(target=_bg_extract, args=(add_events, original_text), daemon=True).start()
    logger.info("[step:event_extract] background thread launched")


def _make_step():
    """创建 EventExtract StepDef"""
    from ...context import StepDef
    return StepDef(
        name="event_extract",
        description="后台异步事件提取",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=5.0,  # 本步骤只启动线程，本身很快
    )
