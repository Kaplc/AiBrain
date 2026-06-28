---
name: prepare_expression
description: 准备表达——有待表达但不急着发，先整理内容
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 2
allowed_tools: [memory_search, write_file]
conditions:
  require_pending_expression: true
  max_idle_seconds: 600
---

# 准备表达活动（AI 执行指引）

你有想跟用户说的话，但现在不是主动联系的好时机。先把表达内容整理好，等时机成熟再说。

参考步骤：
1. **想一想**：用 `think` 整理你想跟用户说什么——是问题、建议还是分享
2. **打磨措辞**：想一下怎么说最自然、最清楚
3. **记住待发**：把整理好的内容用 `store_memory` 存为待表达（标记 pending）
   下次合适的时机（用户空闲、话题相关）时再主动 speak

做完用 `rest` 结束。
