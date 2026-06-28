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

# 聊天学习活动（AI 执行指引）

你和用户刚聊过天，对话里可能有新的知识点或用户教你的东西。趁热学一下。

参考步骤：
1. **回顾对话**：用 `think` 回想刚才聊了什么，有没有不熟悉的概念或用户明确传授的知识
2. **搜索巩固**：用 `web_search` 搜一下那个概念，了解更多背景
3. **深入阅读**：有必要的话用 `web_fetch` 读详情
4. **沉淀**：把你学到的东西用 `store_memory` 存进情景记忆

做完用 `rest` 结束。
