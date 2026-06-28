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

# 维护目标活动（AI 执行指引）

检查你的目标进度，调整优先级。适合精力不太足但还想做点有用的事时做。

参考步骤：
1. **查看当前目标**：回想或 `memory_search` 你有哪些长期目标
2. **评估进展**：用 `think` 评估每个目标的进度——有推进吗？有阻碍吗？
3. **调整优先级**：哪些目标更重要了？哪些可以先放一放？
4. **记录调整**：如果你改变了方向或有了新计划，用 `store_memory` 记下来

做完用 `rest` 结束。
