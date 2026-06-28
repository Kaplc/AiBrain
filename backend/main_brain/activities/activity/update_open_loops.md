---
name: update_open_loops
description: 整理未完成任务——审视 open_loops.md，更新进展或归档已解决的事项
handler_name: update_open_loops
tick_types: [long_tick, daily_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: [read_file, write_file, memory_search, store_memory]
conditions:
  min_idle_seconds: 900
  require_open_loops_or_goals: true
---

# 整理未完成任务（AI 执行指引）

你有一些还没想明白的事挂在 open_loops 里——也许有些已经解决了，也许有了新进展。

参考步骤：
1. **读当前记录**：用 `read_file` 读 `prompts/identity/open_loops.md`
2. **逐个回顾**：用 `memory_search` 搜每个未解决问题的相关记忆
3. **分类处理**：
   - 已经弄明白的 → 移到"已解决"区
   - 有新线索的 → 更新进展描述
   - 不再关心的 → 直接移除
   - 仍然在意的 → 保持，更新备注
4. **改**：用 `write_file` 写回 `prompts/identity/open_loops.md`
5. **记住**：用 `store_memory` 记下这次整理

做完了用 `rest` 结束。
