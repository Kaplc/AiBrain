---
name: update_goals
description: 更新阶段性目标——审视 goals.md，调整优先级或新增目标
handler_name: update_goals
tick_types: [long_tick, daily_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: [read_file, write_file, memory_search, store_memory]
conditions:
  min_idle_seconds: 1200
  require_open_loops_or_goals: true
---

# 更新目标（AI 执行指引）

你的长期目标不是一成不变的——发现某个目标不再重要、或者有了新方向的时候，可以主动调整。

参考步骤：
1. **读当前目标**：用 `read_file` 读 `prompts/identity/goals.md`
2. **回顾进展**：用 `memory_search` 搜和当前目标相关的记忆，看看有没有进展
3. **思考**：用 `think` 判断哪些目标还在意、哪些该调整、有没有新目标要加
4. **改**：用 `write_file` 写回 `prompts/identity/goals.md`
5. **记住**：用 `store_memory` 记下这次调整

做完了用 `rest` 结束。
