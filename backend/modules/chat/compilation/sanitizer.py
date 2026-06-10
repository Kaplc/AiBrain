"""
sanitizer — Tool Call / Tool Result 对校验

职责：
    在 Tool Loop 每轮调用 complete_with_tools 前执行，修复孤儿对：
    - assistant(tool_calls) 无对应 tool(result) → 移除
    - tool(result) 无对应 assistant(tool_calls) → 移除

用法：
    from modules.chat.compilation.sanitizer import sanitize_tool_pairs
    msgs = sanitize_tool_pairs(msgs)
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def sanitize_tool_pairs(msgs: List[Dict]) -> List[Dict]:
    """校验 tool_call/tool_result 成对，移除孤儿消息

    遍历 msgs，收集所有 tool_call_id：
      - called_ids：assistant(tool_calls) 中声明的 id 集合
      - result_ids：tool(result) 中携带的 tool_call_id 集合
    取交集 valid_ids，只保留引用 valid_ids 的消息。

    Args:
        msgs: 当前工具循环的 messages 列表

    Returns:
        过滤后的 messages 列表（仅移除孤儿，不影响其他消息）
    """
    if not msgs:
        return msgs

    # 第一步：收集所有 tool_call_id
    called_ids: set = set()      # assistant 声明的调用 id
    result_ids: set = set()      # tool 返回的结果 id

    for msg in msgs:
        role = msg.get("role", "")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                cid = tc.get("id")
                if cid:
                    called_ids.add(cid)
        elif role == "tool":
            cid = msg.get("tool_call_id", "")
            if cid:
                result_ids.add(cid)

    # 第二步：有效 id = 既有声明又有结果
    valid_ids = called_ids & result_ids

    orphan_calls = called_ids - valid_ids
    orphan_results = result_ids - valid_ids

    if orphan_calls or orphan_results:
        logger.info(
            f"[sanitizer] removing orphan pairs: "
            f"{len(orphan_calls)} unmatched tool_calls, "
            f"{len(orphan_results)} unmatched tool results"
        )

    # 第三步：过滤
    result: List[Dict] = []
    for msg in msgs:
        role = msg.get("role", "")
        if role == "assistant" and msg.get("tool_calls"):
            # 至少有一个 tool_call_id 有效才保留
            tc_ids = {tc.get("id") for tc in msg["tool_calls"] if tc.get("id")}
            if tc_ids & valid_ids:
                result.append(msg)
            else:
                logger.debug(
                    f"[sanitizer] removed assistant(tool_calls): "
                    f"ids={tc_ids} (none in valid set)"
                )
        elif role == "tool":
            cid = msg.get("tool_call_id", "")
            if cid in valid_ids:
                result.append(msg)
            else:
                logger.debug(
                    f"[sanitizer] removed tool(result): "
                    f"tool_call_id={cid} (not in valid set)"
                )
        else:
            result.append(msg)

    return result
