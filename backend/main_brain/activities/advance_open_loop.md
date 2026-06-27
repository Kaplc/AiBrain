---
name: advance_open_loop
description: 推进未决问题——检查 open loops 状态，尝试推进或关闭
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 3
allowed_tools: [memory_search, web_search, web_fetch]
conditions:
  min_idle_seconds: 180
  require_open_loops: true
---

# 推进未决问题活动

存在 open loops（未闭环的思考/任务）时，选择优先级最高的一个推进。
走通用 LLM controller 循环（judge → adapter → ...）。
