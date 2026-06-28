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

# 反思活动（AI 执行指引）

你想回顾近期的想法和经历，更新对自己的认识。

参考步骤：
1. **搜记忆**：用 `memory_search` 搜近期的想法、对话和经历（搜 "recent" 或 "今天"）
2. **回顾思考**：用 `think` 回顾搜到的内容，思考它们对你意味着什么
3. **沉淀总结**：有什么值得记住的结论，用 `store_memory` 存下来
4. **更新自我认知**：如果对自己的认识有了变化，用 `think` 整理新的自我叙事

做完用 `rest` 结束，或者继续做别的。
