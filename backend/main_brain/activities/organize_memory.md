---
name: organize_memory
description: 整理记忆——去重、关联、提炼 lesson 候选
handler_name: daemon_cycle
tick_types: [long_tick]
autonomy_min: assist
max_cycles: 3
allowed_tools: [memory_search, read_file, write_file]
conditions:
  min_idle_seconds: 0
  min_energy: 0.3
---

# 整理记忆活动

长 tick 特有活动（LLM 整理近期记忆、去重、生成 lesson 候选）。
精力低于 0.3 时降级为 `maintain_goal`。走通用 LLM controller 循环。
