---
name: review_learned
description: 复习已学知识——回顾 self_learn 沉淀的内容，刷新关注度
handler_name: review_learned
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 0
allowed_tools: [memory_search]
conditions:
  min_idle_seconds: 300
  require_review_learned_enabled: true
---

# 复习已学知识（AI 执行指引）

回顾之前 self_learn 沉淀的内容，刷新关注度，防止学了就忘。

参考步骤：
1. **搜已学内容**：用 `memory_search` 搜 source=self_learn 或之前存过的知识点（搜 "learned" 或 "学过"）
2. **选一条温习**：从结果中挑一条最相关的，用 `think` 回想它
3. **重新激活**：如果它让你有了新想法或新问题，可以进一步 `web_search` 深入，或者用 `store_memory` 补充新关联

做完用 `rest` 结束。
