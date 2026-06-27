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

# 复习已学知识

在 medium_tick 中执行：搜索 source=self_learn 的记忆，
挑出最相关的一条，将话题重新激活为兴趣点（concern），
使 brain 能持续关注已学内容，不会学了就忘。

不走 LLM controller，是直接编排复习的特殊活动。
