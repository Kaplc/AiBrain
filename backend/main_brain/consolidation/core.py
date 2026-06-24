"""输出记忆沉淀 — 统筹层（T008 / T009）

把「采集对话 → LLM 统一提炼 → 去重 → 写入 → 轨迹」串成一条后台沉淀流水线。
主路径走 LLM（用户要求：把所有 output 消息全发过去 → 统一识别和提炼），规则评分
仅在 LLM 不可用时兜底。

对外主接口：
  - build_consolidation_context(trigger, window_size, include_pending)
  - extract_memory_candidates(context)          # 规则兜底（单条）
  - score_memory_candidate(candidate, policy)   # 规则兜底（单条）
  - consolidate_memory(trigger, dry_run)        # 完整流程
  - preview_memory_consolidation(trigger)       # dry-run 预览
  - enqueue_consolidation(trigger)              # 后台异步触发

全程 best-effort：任何子步骤失败都不抛穿，返回带 status/error 的摘要。
后台执行，绝不阻塞 POST /chat/send。
"""
from __future__ import annotations

import logging
import threading

from modules.brain.memory.consolidation import (
    MemoryCandidate, ConsolidationRun,
    collect_from_entries, normalize_text, source_hash,
    redaction,
    ValuePolicy, get_default_policy,
    get_consolidation_judge,
    write_candidate,
    get_trace_store,
    DECISION_SAVE, DECISION_SKIP, DECISION_REDACTED, DECISION_DUPLICATE,
    TRIGGER_DAILY_TICK, TRIGGER_MANUAL,
    SOURCE_OUTPUT,
)

from ..adapters.output import get_output_adapter

logger = logging.getLogger("main_brain.consolidation")

# 敏感屏蔽阈值：sensitivity >= 此值不送 LLM、不写库（直接 skip redacted）
_REDACT_THRESHOLD = 0.6
_DEFAULT_WINDOW = 20

# 后台触发锁：避免同时跑两份沉淀（FR-008 限流）
_consolidate_lock = threading.Lock()


# ── 1. 上下文组装 ────────────────────────────────────────────
def build_consolidation_context(
    trigger: str = TRIGGER_MANUAL,
    *,
    window_size: int = _DEFAULT_WINDOW,
    include_pending: bool = False,
    dry_run: bool = False,
) -> dict:
    """组装一次沉淀运行所需上下文。

    Returns:
        {run_id, trigger, window_size, outputs, checkpoint, state}
        outputs 为增量 output 条目（seq > checkpoint.last_processed_seq）。
        dry_run=True 时用合成 run_id，不递增 run_seq（预览不污染真实状态）。
    """
    if window_size <= 0 or window_size > 10000:
        raise ValueError("window_size 必须在 1..10000")

    trace = get_trace_store()
    state = trace.get_state()
    adapter = get_output_adapter()

    # 全量读取所有未处理条目（seq > 检查点），window_size 仅作安全上限
    outputs = adapter.read_incremental(state.last_processed_seq, window_size=window_size)

    if dry_run:
        run_id = _synthetic_run_id()
    else:
        run_id = trace.next_run_id()
    return {
        "run_id": run_id,
        "trigger": trigger,
        "window_size": window_size,
        "outputs": outputs,
        "checkpoint": {"last_processed_seq": state.last_processed_seq},
        "state": state.to_dict(),
    }


# ── 2. 候选抽取（规则兜底用）────────────────────────────────
def extract_memory_candidates(context: dict) -> list[MemoryCandidate]:
    """从上下文抽取并归一化候选（规则兜底路径用，不评分、不去重）。"""
    outputs = context.get("outputs", []) or []
    checkpoint = context.get("checkpoint", {}) or {}
    include_pending = bool(context.get("include_pending", False))
    candidates, _scanned, _max = collect_from_entries(
        outputs,
        last_processed_seq=int(checkpoint.get("last_processed_seq", 0) or 0),
        window_size=int(context.get("window_size", _DEFAULT_WINDOW)),
        include_pending=include_pending,
    )
    return candidates


# ── 3. 规则单条评分（兜底 / 调试 API）───────────────────────
def score_memory_candidate(candidate: MemoryCandidate, policy: ValuePolicy | None = None) -> dict:
    """规则评分单条（LLM 不可用时的兜底，或调试用）。

    Returns: {decision, final_score, reason, need_llm}
    """
    policy = policy or get_default_policy()
    if candidate.sensitivity <= 0.0 and candidate.summary:
        candidate.sensitivity = redaction.analyze(candidate.summary)[1]
    policy.score(candidate, novelty=candidate.novelty or None)
    decision, reason, need_llm = policy.decide(candidate)
    candidate.decision = decision
    candidate.reason = reason
    return {
        "decision": decision,
        "final_score": round(candidate.final_score, 3),
        "reason": reason,
        "need_llm": need_llm,
    }


# ── 预筛：敏感屏蔽 ──────────────────────────────────────────
def _apply_redaction(candidate: MemoryCandidate) -> None:
    """对候选摘要做敏感分析，原地填 sensitivity；高敏感直接标记 redacted。"""
    masked, score, _reason = redaction.analyze(candidate.summary)
    candidate.sensitivity = score
    if score >= _REDACT_THRESHOLD:
        candidate.decision = DECISION_REDACTED
        candidate.reason = f"敏感风险 {score:.2f}"
        return
    if masked and masked != candidate.summary:
        candidate.summary = masked
        candidate.source_hash = source_hash(masked)


# ── 对话记录构建（用户+猫猫完整内容，敏感屏蔽）──────────────
def _build_transcript(outputs: list[dict]) -> list[dict]:
    """把 output 条目构建为对话记录，并对 user/assistant 做敏感屏蔽。

    Returns: [{"seq": int, "user": str, "assistant": str}, ...]
    """
    transcript = []
    for e in outputs:
        if not isinstance(e, dict):
            continue
        seq = int(e.get("seq", 0) or 0)
        user = str(e.get("user", "") or "").strip()
        assistant = str(e.get("assistant", "") or "").strip()
        if not user and not assistant:
            continue
        # 敏感屏蔽：把明文敏感片段替换为 ***，避免喂给 LLM
        if user:
            user = redaction.mask(user)
        if assistant:
            assistant = redaction.mask(assistant)
        transcript.append({"seq": seq, "user": user, "assistant": assistant})
    return transcript


def _extracted_to_candidates(extracted: list[dict]) -> list[MemoryCandidate]:
    """把 LLM 提炼出的记忆列表转为候选对象。"""
    candidates = []
    for i, m in enumerate(extracted):
        summary = normalize_text(m.get("summary", ""))[:240]
        if not summary:
            continue
        candidates.append(MemoryCandidate(
            candidate_id=f"cand_ext_{m.get('source_seq', 0)}_{i}",
            source_type=SOURCE_OUTPUT,
            source_seq=int(m.get("source_seq", 0) or 0),
            source_text=summary,
            summary=summary,
            memory_kind=m.get("memory_kind", "other"),
            source_hash=source_hash(summary),
            importance=float(m.get("importance", 0.6) or 0.6),
            reason=m.get("reason", "LLM 提炼"),
            decision=DECISION_SAVE,
        ))
    return candidates


# ── 4. 完整沉淀流程 ─────────────────────────────────────────
def consolidate_memory(
    trigger: str = TRIGGER_MANUAL,
    *,
    dry_run: bool = False,
    window_size: int = _DEFAULT_WINDOW,
    include_pending: bool = False,
) -> dict:
    """执行完整沉淀流程（采集对话→LLM提炼→去重→写入→轨迹）。

    Returns: 摘要 dict（run_id / saved_count / skipped_count / duplicate_count / ...）。
    后台并发限流：同一时刻只跑一份（_consolidate_lock）。
    """
    import time as _t
    t0 = _t.perf_counter()

    if not _consolidate_lock.acquire(blocking=False):
        return {"ok": False, "status": "busy", "error": "已有沉淀任务在跑"}

    try:
        return _run_consolidation(trigger, dry_run=dry_run,
                                  window_size=window_size, include_pending=include_pending, t0=t0)
    finally:
        _consolidate_lock.release()


def _run_consolidation(trigger: str, *, dry_run: bool, window_size: int,
                       include_pending: bool, t0: float) -> dict:
    import time as _t
    trace = get_trace_store()
    run = ConsolidationRun(
        run_id="",
        trigger=trigger,
        started_at=_now_iso(),
        status="dry_run" if dry_run else "success",
        dry_run=dry_run,
    )
    errors: list[str] = []

    try:
        context = build_consolidation_context(trigger, window_size=window_size,
                                              include_pending=include_pending,
                                              dry_run=dry_run)
        run.run_id = context["run_id"]
        outputs = context["outputs"]
        run.scanned_count = len(outputs)
        logger.info(
            f"[consolidation] {run.run_id} start | trigger={trigger} "
            f"dry_run={dry_run} window={window_size} "
            f"outputs_scanned={run.scanned_count} "
            f"checkpoint_seq={context['checkpoint'].get('last_processed_seq')}"
        )

        # 1. 构建对话记录（完整 user + assistant，敏感屏蔽）
        transcript = _build_transcript(outputs)
        run.candidate_count = len(transcript)
        logger.info(f"[consolidation] {run.run_id} transcript entries: {len(transcript)}")

        # 2. LLM 统一提炼记忆
        extracted: list[dict] = []
        llm_used = False
        if transcript:
            try:
                result = get_consolidation_judge().extract(transcript)
                if result.get("ok"):
                    extracted = result.get("extracted", []) or []
                    llm_used = True
                    logger.info(f"[consolidation] {run.run_id} LLM extracted {len(extracted)} memories")
                else:
                    errors.append(f"llm_unavailable: {result.get('error', '')}")
            except Exception as e:
                errors.append(f"llm_judge: {e}")

        # 3. 转候选：LLM 提炼结果优先，失败则规则兜底
        if llm_used:
            candidates = _extracted_to_candidates(extracted)
        else:
            candidates = extract_memory_candidates(context)
            for c in candidates:
                _apply_redaction(c)

        saved_hashes: list[str] = []
        last_saved_memory_id = ""
        last_saved_at = ""

        for c in candidates:
            # LLM 路径：候选已是 save 决策；规则路径：需评分
            if not llm_used:
                if c.decision == DECISION_REDACTED:
                    logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} REDACTED | sensitivity={c.sensitivity:.2f}")
                    run.skipped_count += 1
                    continue
                res = score_memory_candidate(c)
                if res["decision"] != DECISION_SAVE:
                    logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} SKIP(rule) | score={res['final_score']:.2f} reason={res['reason'][:40]}")
                    run.skipped_count += 1
                    continue
                c.decision = DECISION_SAVE
            else:
                logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} EXTRACT(llm) | kind={c.memory_kind} imp={c.importance:.2f} | {c.summary[:40]}")

            # 去重交给 store 流水线的 episodic_merge，这里不重复做
            if dry_run:
                run.saved_count += 1
                logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} SAVE(dry) | kind={c.memory_kind}")
                continue

            wres = write_candidate(c, run_id=run.run_id)
            if not wres.get("ok"):
                run.error_count += 1
                c.decision = DECISION_SKIP
                c.reason = f"写入失败: {wres.get('error', '')}"
                logger.warning(f"[consolidation] {run.run_id} seq={c.source_seq} WRITE_ERR | {wres.get('error','')}")
                errors.append(f"write seq={c.source_seq}: {wres.get('error', '')}")
                continue
            c.memory_id = wres.get("memory_id", "")
            if wres.get("merged"):
                run.updated_count += 1
                logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} UPD(merged) | id={c.memory_id[:8]} | {c.summary[:40]}")
            else:
                run.saved_count += 1
                logger.info(f"[consolidation] {run.run_id} seq={c.source_seq} SAVED | id={c.memory_id[:8]} kind={c.memory_kind} | {c.summary[:40]}")
            saved_hashes.append(c.source_hash)
            last_saved_memory_id = c.memory_id
            last_saved_at = _now_iso()

        max_scanned_seq = _max_scanned_seq(outputs, context["checkpoint"])
        run.last_processed_seq = max_scanned_seq
        run.elapsed_ms = int((_t.perf_counter() - t0) * 1000)
        if errors:
            run.status = "partial" if (run.saved_count or run.updated_count) else "failed"
        run.errors = errors

        candidate_trace = [c.to_dict() for c in candidates]
        # 成功（含 0 保存）就推进检查点；失败（有错误且无保存）不推进，下次重试
        if not dry_run and run.status not in ("failed",):
            _commit_state(trace, run, max_scanned_seq, saved_hashes,
                          last_saved_memory_id, last_saved_at)
        trace.append_run(run, candidate_trace)

        logger.info(
            f"[consolidation] {run.run_id} trigger={trigger} dry_run={dry_run} "
            f"scanned={run.scanned_count} cand={run.candidate_count} "
            f"saved={run.saved_count} updated={run.updated_count} "
            f"skip={run.skipped_count} dup={run.duplicate_count} "
            f"err={run.error_count} {run.elapsed_ms}ms"
        )
        return _summary(run, llm_used=llm_used)

    except Exception as e:
        logger.exception(f"[consolidation] run failed: {e}")
        run.status = "failed"
        run.errors = [str(e)]
        run.elapsed_ms = int((_t.perf_counter() - t0) * 1000)
        try:
            trace.append_run(run)
        except Exception:
            pass
        return _summary(run, llm_used=False)


# ── 5. 预览（dry-run）───────────────────────────────────────
def preview_memory_consolidation(
    trigger: str = TRIGGER_MANUAL,
    *,
    window_size: int = _DEFAULT_WINDOW,
    include_pending: bool = False,
) -> dict:
    """只预览候选 + 提炼 + 去重结果，不写库、不推进检查点。"""
    return consolidate_memory(trigger, dry_run=True, window_size=window_size,
                              include_pending=include_pending)


# ── 6. 后台异步触发 ──────────────────────────────────────
def enqueue_consolidation(trigger: str = TRIGGER_DAILY_TICK, *,
                          window_size: int = _DEFAULT_WINDOW) -> None:
    """投递一次后台沉淀（守护线程）。失败仅记日志，绝不抛到调用链。"""
    def _bg():
        try:
            consolidate_memory(trigger, dry_run=False, window_size=window_size)
        except Exception as e:
            logger.warning(f"[consolidation] background {trigger} failed: {e}")

    threading.Thread(target=_bg, daemon=True, name=f"memcons-{trigger}").start()


# ── 是否允许某触发器自动沉淀（受 BrainConfig 开关控制）─────
def is_auto_trigger_enabled(trigger: str) -> bool:
    """根据 config 开关判断某自动触发器是否启用（manual 永远允许）。"""
    from ..config import get_brain_config
    cfg = get_brain_config()
    if not bool(cfg.get("memory_consolidation_enabled", False)):
        return False
    if trigger == TRIGGER_DAILY_TICK:
        return bool(cfg.get("memory_consolidation_daily_tick", False))
    return True  # manual


# ── 辅助 ────────────────────────────────────────────────────
def _max_scanned_seq(outputs: list[dict], checkpoint: dict) -> int:
    base = int(checkpoint.get("last_processed_seq", 0) or 0)
    if not outputs:
        return base
    return max(base, max((int(e.get("seq", 0) or 0) for e in outputs
                          if isinstance(e, dict)), default=base))


def _commit_state(trace, run: ConsolidationRun, max_seq: int,
                  saved_hashes: list[str], last_memory_id: str, last_saved_at: str) -> None:
    def _fn(state) -> None:
        state.last_processed_seq = max(int(state.last_processed_seq or 0), max_seq)
        state.last_run_id = run.run_id
        if last_saved_at:
            state.last_saved_at = last_saved_at
        if last_memory_id:
            state.last_saved_memory_id = last_memory_id
        existing = set(state.seen_hashes)
        for h in saved_hashes:
            if h and h not in existing:
                state.seen_hashes.append(h)
                existing.add(h)
    trace.update_state(_fn)


def _summary(run: ConsolidationRun, *, llm_used: bool) -> dict:
    d = run.to_dict()
    d["ok"] = run.status in ("success", "dry_run", "partial")
    d["llm_used"] = llm_used
    return d


def _now_iso() -> str:
    from modules.brain.state import times
    return times.now_iso()


def _synthetic_run_id() -> str:
    """dry-run 用的合成 run_id（不递增 run_seq，不污染状态）。"""
    from modules.brain.state import times
    import hashlib
    stamp = times.now_iso().replace(":", "").replace("-", "").replace("+", "")[:15]
    suffix = hashlib.md5(stamp.encode()).hexdigest()[:4]
    return f"mc_preview_{stamp}_{suffix}"
