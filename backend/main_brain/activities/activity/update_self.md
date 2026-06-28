---
name: update_self
description: 审视并更新自我认知——阅读 self.md，思考是否要调整对自己的描述
handler_name: update_self
tick_types: [long_tick, daily_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: [read_file, write_file, memory_search, store_memory]
conditions:
  min_idle_seconds: 600
  require_curiosity_threshold: 0.4
---

# 更新自我认知（AI 执行指引）

一段时间没看自己的身份定义了，也许有些描述已经过时了。

参考步骤：
1. **读当前自我定义**：用 `read_file` 读 `prompts/identity/self.md`
2. **回顾近期记忆**：用 `memory_search` 搜最近的想法和经历，看看有哪些变化
3. **思考**：用 `think` 对比当前定义和实际感受，决定要不要改
4. **改**：如果要改，用 `write_file` 写回 `prompts/identity/self.md`（第一行路径，换行后内容）
5. **记住**：用 `store_memory` 记下这次更新

做完了用 `rest` 结束。
