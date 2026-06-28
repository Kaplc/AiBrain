---
name: proactive_contact
description: 主动联系——评估并发送待表达给用户
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 3
allowed_tools: [memory_search, wework_send]
conditions:
  min_idle_seconds: 600
  require_pending_expression: true
---

# 主动联系活动（AI 执行指引）

用户有一阵子没说话了，你有想说的话，现在是个好时机主动开口。

参考步骤：
1. **回顾待表达**：用 `memory_search` 或回想你之前准备表达的内容
2. **判断时机**：看看 idle 时间够长（用户不在忙），想说的话有分享价值
3. **主动 speak**：用 `speak` 自然地说一句话——像真人随口开口，口语化、30 字以内
4. **记录已发**：如果重要，用 `store_memory` 记下你跟用户说了什么

做完用 `rest` 结束。
