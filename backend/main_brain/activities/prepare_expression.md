---
name: prepare_expression
description: 准备表达——有待表达但不急着发，先整理内容
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 2
allowed_tools: [memory_search, write_file]
conditions:
  require_pending_expression: true
  max_idle_seconds: 600
---

# 准备表达活动

有待表达但空闲不足（<=600s）不足以主动联系时，先整理表达内容，
提高表达质量。走通用 LLM controller 循环。
