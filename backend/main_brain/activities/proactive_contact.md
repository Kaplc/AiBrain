---
name: proactive_contact
description: 主动联系——评估并发送待表达给用户
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 3
allowed_tools: [memory_search, wework_send]
conditions:
  min_idle_seconds: 600
  require_pending_expression: true
---

# 主动联系活动

有空闲 + 有待表达时，走 ExpressionGate 评估是否值得主动发送。
本质是走通用 LLM controller 循环，但最后落到表达闸门评估。
