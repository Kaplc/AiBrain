---
name: use_tool
description: 工具调用——自主调用白名单工具完成任务
handler_name: daemon_cycle
tick_types: [medium_tick, long_tick, manual_tick]
autonomy_min: assist
max_cycles: 5
allowed_tools: [memory_search, web_search, web_fetch, bash, read_file, write_file, patch, execute_code, wework_send]
conditions:
  min_idle_seconds: 60
---

# 工具调用活动

有明确工具调用需求时使用。走通用 LLM controller 循环，
由 BrainJudge 决定具体调什么工具。
