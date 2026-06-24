"""输出记忆沉淀 — 调试 / 回放（T011 / T012）

提供三类离线工具，便于调阈值与回归测试，不依赖真实聊天：
  - probe()                          ：当前状态 + 最近运行快照
  - preview(trigger, window_size)    ：dry-run 预览（不写库、不推进检查点）
  - run_replay(samples, ...)         ：用固定样本回放决策链
      （采集→敏感屏蔽→LLM/规则判断→去重），覆盖保存/跳过/去重/敏感过滤

回放复用 collector / redaction / policy / judge / dedupe，不触碰真实 output.json、
不写库、不推进检查点，纯决策验证（FR-012）。

可独立运行：
    python -m main_brain.testing.memory_consolidation
"""
from __future__ import annotations

import logging

from modules.brain.memory.consolidation import (
    MemoryCandidate,
    collect_from_entries, redaction, source_hash,
    ValuePolicy, get_default_policy,
    get_consolidation_judge,
    DedupeGate,
    get_trace_store,
    DECISION_SAVE, DECISION_SKIP, DECISION_REDACTED, DECISION_DUPLICATE,
)

logger = logging.getLogger("main_brain.testing.memory_consolidation")


def probe() -> dict:
    """当前沉淀状态 + 最近运行（调试快照）。"""
    trace = get_trace_store()
    state = trace.get_state()
    return {
        "state": state.to_dict(),
        "recent_runs": trace.recent_runs(limit=10),
        "log_path": trace.log_path(),
    }


def preview(trigger: str = "manual", *, window_size: int = 20) -> dict:
    """dry-run 预览（委托 orchestrator，不写库、不推进检查点）。"""
    from main_brain.consolidation import preview_memory_consolidation
    return preview_memory_consolidation(trigger, window_size=window_size)


def run_replay(
    samples: list[dict],
    *,
    mock_llm: str | None = None,
    use_llm: bool = True,
    semantic_check: bool = False,
    policy: ValuePolicy | None = None,
) -> dict:
    """用固定样本回放决策链。

    Args:
        samples: 形如 output.json 条目 [{"seq":1,"user":"...","assistant":"...","time":"..."}]
        mock_llm: 传入则用该字符串作为 LLM 返回（mock，不真实调用），形如
                  '{"results":[{"index":0,"save":true,"summary":"...","memory_kind":"preference","importance":0.8}]}'
        use_llm: True 走 LLM 判断（mock_llm 非空时用它），False 走规则评分。
        semantic_check: 是否在去重阶段做语义检索（回放默认关，避免依赖 Qdrant）。

    Returns:
        {
            "candidates": [候选决策明细...],
            "counts": {save, skip, redacted, duplicate},
            "llm_used": bool,
        }
    """
    policy = policy or get_default_policy()

    # 构建对话记录（敏感屏蔽）
    transcript = []
    for e in samples:
        if not isinstance(e, dict):
            continue
        user = str(e.get("user", "") or "").strip()
        assistant = str(e.get("assistant", "") or "").strip()
        if user:
            user = redaction.mask(user)
        if assistant:
            assistant = redaction.mask(assistant)
        if user or assistant:
            transcript.append({"seq": int(e.get("seq", 0) or 0), "user": user, "assistant": assistant})

    # LLM 统一提炼（或规则兜底）
    llm_used = False
    candidates: list = []
    if use_llm:
        res = get_consolidation_judge().extract(transcript, mock_response=mock_llm)
        llm_used = bool(res.get("ok"))
        if llm_used:
            for i, m in enumerate(res.get("extracted", []) or []):
                summary = (m.get("summary") or "").strip()[:240]
                if not summary:
                    continue
                candidates.append(MemoryCandidate(
                    candidate_id=f"cand_ext_{m.get('source_seq', 0)}_{i}",
                    source_seq=int(m.get("source_seq", 0) or 0),
                    summary=summary,
                    memory_kind=m.get("memory_kind", "other"),
                    source_hash=source_hash(summary),
                    importance=float(m.get("importance", 0.6) or 0.6),
                    reason=m.get("reason", "LLM 提炼"),
                    decision=DECISION_SAVE,
                ))

    if not llm_used:
        # 规则兜底：从 user 文本抽候选
        rule_cands, _s, _m = collect_from_entries(samples, last_processed_seq=0,
                                                  window_size=len(samples) or 20)
        for c in rule_cands:
            masked, score, _r = redaction.analyze(c.summary)
            c.sensitivity = score
            if score >= 0.6:
                c.decision = DECISION_REDACTED
                c.reason = f"敏感风险 {score:.2f}"
                candidates.append(c)
                continue
            if masked and masked != c.summary:
                c.summary = masked
            policy.score(c, novelty=c.novelty or None)
            decision, reason, _need = policy.decide(c)
            c.decision = decision
            c.reason = reason
            candidates.append(c)

    gate = DedupeGate(seen_hashes=set(), semantic_check=semantic_check)

    for c in candidates:
        if c.decision == DECISION_REDACTED:
            continue
        if c.decision != DECISION_SAVE:
            continue

        status, novelty, dedup_reason = gate.check(c)
        c.novelty = novelty
        if status == "duplicate":
            c.decision = DECISION_DUPLICATE
            c.reason = dedup_reason or "重复"

    counts = {
        DECISION_SAVE: sum(1 for c in candidates if c.decision == DECISION_SAVE),
        DECISION_SKIP: sum(1 for c in candidates if c.decision == DECISION_SKIP),
        DECISION_REDACTED: sum(1 for c in candidates if c.decision == DECISION_REDACTED),
        DECISION_DUPLICATE: sum(1 for c in candidates if c.decision == DECISION_DUPLICATE),
    }
    return {
        "candidates": [c.to_dict() for c in candidates],
        "counts": counts,
        "llm_used": llm_used,
    }


# ── 内置回放样本（覆盖保存/跳过/敏感/重复）──────────────────
_DEMO_SAMPLES = [
    {"seq": 1, "user": "我喜欢用 VSCode 写代码，以后都用它", "assistant": "好的", "time": "2026-06-24 10:00:00"},  # 偏好→save
    {"seq": 2, "user": "你好呀", "assistant": "你好！", "time": "2026-06-24 10:01:00"},                            # 闲聊→skip
    {"seq": 3, "user": "我的 api_key=sk-abcdef1234567890 请记住", "assistant": "好的", "time": "2026-06-24 10:02:00"},  # 敏感→redacted
    {"seq": 4, "user": "下次记得帮我整理一下记忆库", "assistant": "好的", "time": "2026-06-24 10:03:00"},          # 任务→save
    {"seq": 5, "user": "我喜欢用 VSCode 写代码，以后都用它", "assistant": "好的", "time": "2026-06-24 10:04:00"},  # 重复(同hash)→duplicate
]


def demo() -> dict:
    """跑内置样本（规则模式，不依赖 LLM/Qdrant），演示四类决策。"""
    logging.basicConfig(level=logging.INFO)
    result = run_replay(_DEMO_SAMPLES, use_llm=False, semantic_check=False)
    print("=== 记忆沉淀回放（规则模式）===")
    for c in result["candidates"]:
        print(f"  seq={c['source_seq']:>2} {c['decision']:<10} "
              f"分={c['final_score']:.2f} kind={c['memory_kind']:<10} "
              f"| {c['summary'][:40]}")
    print("counts:", result["counts"])
    return result


if __name__ == "__main__":
    demo()
