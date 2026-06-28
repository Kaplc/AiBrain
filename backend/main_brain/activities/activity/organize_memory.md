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

# 整理记忆活动（AI 执行指引）

整理你的长期记忆——去重、关联、提炼经验。适合有一段安静时间时做。

参考步骤：
1. **搜近期记忆**：用 `memory_search` 搜最近的经历和学到的知识
2. **去重关联**：如果发现重复或相关的记忆，用 `think` 整理它们之间的关系
3. **提炼经验**：从经历中总结出 lesson / 经验，用 `store_memory` 单独存为一条经验知识
4. **归档清理**：过时或不准确的信息可以不用管，新存入的更好信息自然覆盖

做完用 `rest` 结束。
