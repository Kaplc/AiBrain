---
name: maintain_goal
description: 维护目标——检查目标进度、调整优先级
handler_name: daemon_cycle
tick_types: [long_tick]
autonomy_min: assist
max_cycles: 2
allowed_tools: [memory_search, write_file]
conditions:
  min_idle_seconds: 0
---

# 维护目标活动

长 tick 精力低时降级至此。检查 goals 列表的状态，调整优先级。
走通用 LLM controller 循环。
