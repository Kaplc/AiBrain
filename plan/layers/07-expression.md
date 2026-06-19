# 表达/行动层 (Expression / Action Layer)

## 一、项目目标

- **项目名称**：表达/行动层
- **一句话描述**：main_brain 8 层架构的第 7 层。大脑的输出接口——决定说什么、怎么说、说不说（三级过滤）。
- **核心目标**：
  1. 三级输出分级：internal（仅log）/ seed（入 pending）/ send（直接发）
  2. 接管现有 proactive_send 逻辑，迁移到本层
  3. 内心独白生成 + 表达决策
  4. 输出内容到 output.json / SSE / inner_monologue.jsonl
- **不做的事**：
  - 不决定"想什么"（那是 Cognition Layer）
  - 不改变前端 SSE 协议

## 二、现有基础

- `modules/brain/state/pending_expression.py` — PendingExpressionManager（proactive_send / evaluate_and_generate / pick_to_send）
- `modules/brain/state/expression_history.py` — 24h 冷却
- `modules/brain/memory/workmemory/workmemory.py` — output_mem_write

## 三、三级输出

| 级别 | 去向 | 前端可见 | 频率 |
|------|------|---------|------|
| internal | inner_monologue.jsonl | ❌ | ~3min |
| seed | pending_expression 队列 | ❌（等待升级） | ~3min |
| send | output.json + SSE | ✅ | 按冷却规则 |

## 四、文件清单

```
backend/main_brain/expression/
  __init__.py
  output.py         # 输出器（写 output.json + SSE）
  monologue.py      # 内心独白生成（LLM）
  pending.py        # 迁移 PendingExpressionManager
  refractory.py     # 迁移 ExpressionHistoryManager
  buffer.py         # 输出缓存 + flush
```
