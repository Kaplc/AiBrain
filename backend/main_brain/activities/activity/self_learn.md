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

# 自主学习活动（AI 执行指引）

好奇心驱动的主动学习。你想自己选个话题，搜索了解，然后记住它。

参考步骤：
1. **选话题**：想一个你好奇但不太了解的话题，或者用 `memory_search` 找之前留下但未深究的问题
2. **搜索**：用 `web_search` 搜这个话题，获取背景信息
3. **深入阅读**：如果搜到了有意思的页面，用 `web_fetch` 读详细内容
4. **消化沉淀**：用 `think` 总结你学到了什么
5. **记住**：把学到的知识点用 `store_memory` 存进长期记忆

做完用 `rest` 结束。
