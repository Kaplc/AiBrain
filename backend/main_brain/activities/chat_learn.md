---
name: chat_learn
description: 聊天学习——从对话中提取新知识点，搜索巩固并沉淀为记忆
handler_name: chat_learn
tick_types: [manual_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: [memory_search, web_search, web_fetch, bash, read_file, write_file, patch, execute_code, wework_send]
conditions:
  require_recent_chat: true
---

# 聊天学习活动

在聊天互动后触发。从对话上下文中识别不熟悉的概念或用户明确传授的知识点，
自动 web_search → web_fetch → 提炼摘要 → 存入情景记忆。

不走 LLM controller，是直接编排学习的特殊活动（`daemon._run_chat_learn_activity`）。
与 `self_learn` 不同：self_learn 是后台 tick 空闲时主动选话题学，chat_learn 是聊天后被动触发学。
