---
name: wait
description: 安静等待——无值得做的事，更新 idle/energy 后休眠
handler_name: wait
tick_types: [short_tick, medium_tick, long_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: []
conditions: {}
---

# 等待活动

默认 fallback 活动。不做任何 LLM 调用，只更新 idle_seconds 和 energy。
short_tick 固定返回 wait。
