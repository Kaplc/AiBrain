"""候选采集与归一化（T003 / T004）

从 output.json 增量读取输出条目（seq > last_processed_seq），抽取候选记忆：
  - 主要来源：每条 output 的 user 文本（用户偏好 / 任务 / 约定 / 事实在此）
  - 主动来源：无 user 的输出条目（主动表达），可选纳入（include_pending）
  - 反思 / tick 摘要：预留接口，v1 不默认启用

归一化：清洗空白、去 emoji 噪声、截断；source_hash = sha256(归一化文本)。
不在此评分（policy 负责），不在此去重（dedupe 负责），只产出干净的候选对象。

注意：不读取全量历史，只取 seq 增量 + 窗口上限（FR-001：先支持最近窗口）。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from .contracts import (
    MemoryCandidate, OutputEntry,
    SOURCE_OUTPUT, SOURCE_PROACTIVE, MEMORY_KIND_OTHER,
)

# 太短的候选直接丢弃（信息量不足）：去空白后少于 N 字符
_MIN_TEXT_LEN = 4
# 摘要最大长度（写入用）
_SUMMARY_MAX = 240

# 清洗：连续空白折叠、首尾空白
_WS_RE = re.compile(r"\s+")
# 明显噪声表情/控制字符（保留中日韩与常规标点）
_NOISE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_text(text: str) -> str:
    """归一化：NFKC + 去控制字符 + 折叠空白 + 截断。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = _NOISE_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def source_hash(text: str) -> str:
    """归一化文本的 sha256，作为源头去重键。"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:24]


def _candidate_id(seq: int, idx: int) -> str:
    return f"cand_seq{seq}_{idx}" if seq else f"cand_{idx}"


def collect_from_entries(
    entries: list[dict],
    *,
    last_processed_seq: int = 0,
    window_size: int = 20,
    include_pending: bool = False,
) -> tuple[list[MemoryCandidate], list[OutputEntry], int]:
    """从 output 条目采集候选（增量）。

    Args:
        entries: output_mem_read() 原始条目（含 seq/user/assistant/time）。
        last_processed_seq: 已处理到的 seq，只取大于它的条目。
        window_size: 本次最多扫描的增量条目数（避免长扫）。
        include_pending: 是否把无 user 的主动输出纳入候选。

    Returns:
        (candidates, scanned_entries, new_max_seq)
        scanned_entries 为本次实际扫描的 OutputEntry 列表（含被跳过的）。
        new_max_seq 为本次扫描到的最大 seq（用于推进检查点；无新增返回旧值）。
    """
    # 过滤出增量条目，按 seq 升序
    incremental = [
        e for e in entries
        if isinstance(e, dict) and int(e.get("seq", 0) or 0) > last_processed_seq
    ]
    incremental.sort(key=lambda e: int(e.get("seq", 0) or 0))
    # 窗口上限
    incremental = incremental[:window_size]

    scanned: list[OutputEntry] = []
    candidates: list[MemoryCandidate] = []
    max_seq = last_processed_seq

    for raw in incremental:
        oe = OutputEntry.from_raw(raw)
        scanned.append(oe)
        max_seq = max(max_seq, oe.seq)

        # 主候选：user 文本
        if oe.user:
            cand = _build_candidate(oe, oe.user, idx=len(candidates))
            if cand:
                candidates.append(cand)
        # 主动输出（无 user）可选纳入：取 assistant 但通常低信息，默认关
        elif include_pending and oe.assistant:
            cand = _build_candidate(oe, oe.assistant, idx=len(candidates),
                                    source_type=SOURCE_PROACTIVE)
            if cand:
                candidates.append(cand)

    return candidates, scanned, max_seq


def _build_candidate(
    oe: OutputEntry, text: str, *, idx: int,
    source_type: str = SOURCE_OUTPUT,
) -> MemoryCandidate | None:
    """把一段文本归一化为候选；太短则返回 None。"""
    summary = normalize_text(text)
    if len(summary) < _MIN_TEXT_LEN:
        return None
    summary = summary[:_SUMMARY_MAX]
    return MemoryCandidate(
        candidate_id=_candidate_id(oe.seq, idx),
        source_type=source_type,
        source_seq=oe.seq,
        source_text=text[:_SUMMARY_MAX],
        summary=summary,
        memory_kind=MEMORY_KIND_OTHER,  # 由 policy 按 signal 细分
        source_hash=source_hash(summary),
    )
