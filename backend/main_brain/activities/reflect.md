---
name: reflect
description: 自我反思——回顾近期想法、更新自我叙事、沉淀情感标签
handler_name: reflect
tick_types: [medium_tick, daily_tick, manual_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: []
conditions:
  max_recent_thoughts: 2
  daily_reflect: true
---

# 反思活动

调用 `run_reflection()` 回顾近期想法和经历，更新 self_narrative，
调节 mood/valence/arousal。不走 LLM controller，是直接调用反思核心的
特殊活动（`daemon._run_reflect_activity`）。

每日 tick 固定走 reflect，额外触发记忆沉淀 consolidation。
