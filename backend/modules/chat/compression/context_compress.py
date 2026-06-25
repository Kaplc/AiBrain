"""
后台上下文压缩 — 基于 Token 占比触发

触发逻辑：prompt_tokens / MAX_CONTEXT_TOKENS > COMPRESS_TRIGGER_RATIO 时启动后台线程压缩
压缩策略：从末尾按对话对保留最近的对话（估算 token 在安全线以内），压缩之前的旧对话
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_history_lock = threading.Lock()
_need_reload = False


# ── 配置加载 ──────────────────────────────────────────

def _load_config() -> tuple[int, float]:
    """从 compress_config.py 读取配置，失败返回默认值"""
    try:
        from .compress_config import MAX_CONTEXT_TOKENS, COMPRESS_TRIGGER_RATIO
        mt = MAX_CONTEXT_TOKENS if isinstance(MAX_CONTEXT_TOKENS, int) and MAX_CONTEXT_TOKENS > 0 else 4000
        tr = COMPRESS_TRIGGER_RATIO if isinstance(COMPRESS_TRIGGER_RATIO, (int, float)) and 0 < COMPRESS_TRIGGER_RATIO <= 1 else 0.7
        return mt, float(tr)
    except (ImportError, AttributeError):
        return 4000, 0.7


# ── Token 估算 ────────────────────────────────────────

def _estimate_tokens(messages: list[dict]) -> int:
    """估算消息列表的 token 数（中文约 2 字符/token）"""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return int(total_chars / 2 * 1.1)


# ── 压缩范围计算 ─────────────────────────────────────

def _calculate_keep_from(conversation_history: list, target_tokens: int) -> int:
    """从末尾按对话对向前累加 token，返回压缩切割点（对齐到 user 消息边界）

    Args:
        conversation_history: 对话历史
        target_tokens: 保留部分的目标 token 数

    Returns:
        切割点索引（从该位置开始保留）
    """
    if target_tokens <= 0:
        return len(conversation_history)

    acc_tokens = 0
    pair_count = 0

    # 从末尾向前，按对话对（assistant + user）累加
    for i in range(len(conversation_history) - 1, 0, -2):
        # 一对 = user + assistant
        pair_tokens = _estimate_tokens([
            conversation_history[i - 1],  # user
            conversation_history[i],      # assistant
        ])
        acc_tokens += pair_tokens
        pair_count += 1

        if acc_tokens > target_tokens:
            keep_from = len(conversation_history) - (pair_count * 2)
            return max(0, keep_from)

    # 全部保留
    return 0


# ── 主线程调用 ────────────────────────────────────────

def try_spawn_compress(conversation_history: list, prompt_tokens: int = 0) -> bool:
    """主线程调用：判断 Token 占比是否超阈值，是则启动后台线程

    Args:
        conversation_history: _conversation_history 引用
        prompt_tokens: 本次 LLM 调用返回的 prompt_tokens（实际值）

    Returns:
        True 表示已启动后台线程
    """
    if prompt_tokens <= 0:
        return False

    max_tokens, trigger_ratio = _load_config()
    threshold = int(max_tokens * trigger_ratio)
    current_ratio = prompt_tokens / max_tokens if max_tokens > 0 else 0

    if prompt_tokens <= threshold:
        logger.info(
            f"[compress] token check: {prompt_tokens}/{max_tokens} "
            f"({current_ratio:.1%}) <= threshold {threshold}, skip"
        )
        return False

    logger.info(
        f"[compress] token check: {prompt_tokens}/{max_tokens} "
        f"({current_ratio:.1%}) > threshold {threshold} ({trigger_ratio:.0%}), "
        f"spawning background thread"
    )
    t = threading.Thread(
        target=_compress_background,
        args=(conversation_history, prompt_tokens, max_tokens, trigger_ratio),
        daemon=True,
        name="context_compress",
    )
    t.start()
    return True


def _compress_background(conversation_history: list, prompt_tokens: int, max_tokens: int, trigger_ratio: float):
    """后台线程：按 Token 占比计算压缩范围 → 压缩 → 原子写盘 → 改内存 → 设标记"""
    global _need_reload
    try:
        # ── 1. 计算压缩范围 ──
        # 安全线：压缩后目标 token 数（触发阈值的 60%，留出余量）
        target_tokens = int(max_tokens * trigger_ratio * 0.6)
        keep_from = _calculate_keep_from(conversation_history, target_tokens)

        if keep_from == 0:
            logger.info("[compress] nothing to compress, keep_from=0")
            return

        with _history_lock:
            old_entries = list(conversation_history[:keep_from])
            remaining = list(conversation_history[keep_from:])

        if not old_entries:
            return

        compress_pairs = len(old_entries) // 2
        estimated_old_tokens = _estimate_tokens(old_entries)
        estimated_keep_tokens = _estimate_tokens(remaining)

        logger.info(
            f"[compress] ▶ BEFORE: total_pairs={len(conversation_history) // 2}, "
            f"compress={compress_pairs} pairs ({estimated_old_tokens} tokens), "
            f"keep={len(remaining) // 2} pairs ({estimated_keep_tokens} tokens), "
            f"prompt_tokens={prompt_tokens}/{max_tokens} ({prompt_tokens / max_tokens:.1%})"
        )

        # ── 2. 调 Agent 压缩 ──
        try:
            from modules.LLM import get_agent_manager
            agent = get_agent_manager().get("context_compress")
            result = agent.run({"entries": old_entries})
        except Exception as e:
            logger.warning(f"[compress] agent call failed, skip: {e}")
            return

        if not result:
            logger.warning("[compress] agent returned empty, skip")
            return

        # ── 3. 修改内存（先改内存，再写盘） ──
        with _history_lock:
            mem_compressed = []
            for item in result:
                mem_compressed.append({"role": "user", "content": item["user"]})
                mem_compressed.append({"role": "assistant", "content": item["assistant"]})
            conversation_history[:] = mem_compressed + remaining

        estimated_after_tokens = _estimate_tokens(conversation_history)
        after_ratio = estimated_after_tokens / max_tokens if max_tokens > 0 else 0

        logger.info(
            f"[compress] ◀ AFTER: {compress_pairs} pairs -> {len(result)} compressed entries, "
            f"memory={len(conversation_history)} msgs, "
            f"estimated_tokens={estimated_after_tokens}/{max_tokens} ({after_ratio:.1%})"
        )

        # ── 4. 原子写入 output.json ──
        try:
            from main_brain.memory.workmemory import get_work_memory, get_base_dir
            wm = get_work_memory()
            _BASE_DIR = get_base_dir()
            raw = wm.output_mem_read()

            # 构建压缩条目（新 seq 从 max_seq + 1 开始，time 取当前时间）
            max_seq = max((e.get("seq", 0) for e in raw), default=0)
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            compressed_entries = []
            for item in result:
                max_seq += 1
                compressed_entries.append({
                    "seq": max_seq,
                    "user": item["user"],
                    "assistant": item["assistant"],
                    "time": current_time,
                })

            # 保留原始条目 compress_pairs 之后的部分
            new_output = compressed_entries + raw[compress_pairs:]

            fpath = _BASE_DIR / "output.json"
            fd, tmp = tempfile.mkstemp(dir=str(_BASE_DIR), suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(new_output, f, ensure_ascii=False, indent=2)
                os.replace(tmp, fpath)
            except Exception:
                os.unlink(tmp)
                raise

            logger.info(
                f"[compress] output.json updated: {len(raw)} -> {len(new_output)} entries"
            )

        except Exception as e:
            # 写盘失败 → 回滚内存
            logger.warning(f"[compress] output.json write failed, rolling back memory: {e}")
            with _history_lock:
                conversation_history[:] = old_entries + remaining
            return

        # ── 5. 设标记 ──
        _need_reload = True
        logger.info(f"[compress] ✓ completed successfully, _need_reload=True")

    except Exception as e:
        logger.exception(f"[compress] background compress failed: {e}")


def reload_if_needed(conversation_history: list) -> bool:
    """主线程调用：检查标记，需要则从 output.json 重读

    Args:
        conversation_history: _conversation_history 引用

    Returns:
        True 表示执行了重读
    """
    global _need_reload
    if not _need_reload:
        return False

    try:
        from main_brain.memory.workmemory import get_work_memory
        entries = get_work_memory().output_mem_read()

        with _history_lock:
            conversation_history.clear()
            for e in entries:
                if e.get("user"):
                    conversation_history.append({"role": "user", "content": e["user"]})
                if e.get("assistant"):
                    conversation_history.append({"role": "assistant", "content": e["assistant"]})

        _need_reload = False
        estimated_tokens = _estimate_tokens(conversation_history)
        max_tokens, _ = _load_config()
        ratio = estimated_tokens / max_tokens if max_tokens > 0 else 0
        logger.info(
            f"[compress] reloaded from output.json: {len(conversation_history)} msgs, "
            f"estimated_tokens={estimated_tokens}/{max_tokens} ({ratio:.1%})"
        )
        return True

    except Exception as e:
        logger.warning(f"[compress] reload failed: {e}")
        _need_reload = False
        return False
