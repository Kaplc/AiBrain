---
name: use_tool
description: 调用一个工具。tool_name=工具名，tool_args=参数。结果：执行结果注入下一轮，可继续深入
terminates: false
---

# use_tool

调用一个工具观察世界或完成一步探索。**不终止本轮**——结果会注入下一轮，可以继续用工具深入。

**结果**：工具执行结果注入 `【当前任务进度】` 段，你可以在下一轮看到并决定下一步。

可用工具：
- `read_file` —— 读取项目文件内容。tool_args 给相对路径
- `grep_search` —— 在代码库里按正则搜索内容。tool_args 给搜索词
- `memory_search` —— 在自己的长期记忆中搜索。tool_args 用自然语言描述
- `web_search` —— 搜索互联网获取新信息。tool_args 给关键词
- `store_memory` —— 把一段内容存入自己的长期记忆。tool_args 给要记住的文本
- `list_files` —— 列出某个目录下的文件。tool_args 给目录相对路径
