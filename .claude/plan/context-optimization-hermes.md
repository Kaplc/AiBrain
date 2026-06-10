# Context Optimization Plan

---

# 一、目标

1. **Tool Loop 内部健壮性** — 发 API 前校验 tool_call/result 成对
2. **连续多轮工具记忆** — 上一轮的工具结果（原始消息）在内存保留，注入下一轮 `msgs`

# 二、设计

## 模块 1：sanitizer — tool pair 校验

Tool Loop 每轮调 `complete_with_tools` 前执行，修复孤儿对。

## 模块 2：_tool_memory — 内存工具记忆

### 数据流

```
轮1 ── send_message()
  └─ msgs = system + history + memory_ref + Q1
  └─ Tool Loop → msgs 追加 assistant(tool_calls) + tool(result)
  └─ 结束:
       ├─ user + assistant 文本 → _conversation_history
       ├─ 从 msgs 提取 tool 相关消息 → _tool_memory  ← 内存保留
       └─ 不落盘

轮2 ── send_message()
  └─ msgs = system + history + _tool_memory + memory_ref + Q2
                            ↑ 上一轮的工具结果原样注入
  └─ LLM 能看到上一轮的工具执行结果
  └─ 如果这轮也调了工具 → 更新 _tool_memory
  └─ 如果这轮没调工具 → _tool_memory 不变
```

### 生命周期

```
启动          → _tool_memory = []
Tool Loop 结束 → 提取 msgs 中 tool 相关消息 → 替换 _tool_memory
重启          → _tool_memory 丢失
压缩          → 不触及 _tool_memory
持久化        → 不写入 output.json
```

### 保留什么

保存 `msgs` 中 `role` 为 `assistant`（含 tool_calls）和 `tool` 的**原始消息**，不提炼、不摘要：

```python
_tool_memory = [
    msg for msg in msgs
    if msg["role"] in ("assistant", "tool")
    and msg["role"] != "assistant" or msg.get("tool_calls")  # 只保留有 tool_calls 的 assistant 消息
]
```

只保留**最近一轮**的工具消息（每次 Tool Loop 结束替换，不累积）。

# 三、文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/modules/chat/compilation/sanitizer.py` | 新建 | Tool pair 校验 |
| `backend/modules/chat/loop.py` | 修改 | 集成 sanitizer + _tool_memory |

# 四、任务

| ID | 任务 | 复杂度 | 预估 |
|----|------|--------|------|
| T001 | 新建 `sanitizer.py` | S | 30min |
| T002 | `loop.py` 集成 sanitizer | S | 15min |
| T003 | `loop.py` 新增 `_tool_memory` + 提取逻辑 | S | 30min |
| T004 | `loop.py` msgs 构建注入 `_tool_memory` | S | 15min |
