---
name: self_learn
description: 自主学习——选话题、搜索外部知识、沉淀为情景记忆
handler_name: self_learn
tick_types: [medium_tick, long_tick]
autonomy_min: assist
max_cycles: 0
allowed_tools: [web_search, web_fetch, memory_search]
conditions:
  min_idle_seconds: 180
  require_curiosity_threshold: 0.6
  require_open_loops_or_goals: true
---

# 自主学习活动

好奇心驱动的主动学习。编排流程：guard → 选话题 → 搜索 → 沉淀 → 反馈。
不走 LLM controller，是直接编排学习的特殊活动（`daemon._run_self_learn_activity`）。
