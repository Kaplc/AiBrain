---
name: advance_open_loop
description: 推进未决问题——检查 open loops 状态，尝试推进或关闭
handler_name: daemon_cycle
tick_types: [medium_tick]
autonomy_min: assist
max_cycles: 3
allowed_tools: [memory_search, web_search, web_fetch]
conditions:
  min_idle_seconds: 180
  require_open_loops: true
---

# 推进未决问题活动（AI 执行指引）

你有一些未闭环的思考或任务（open loops）。挑一个最要紧的推进它。

参考步骤：
1. **查看 open loops**：用 `memory_search` 搜你当前在意的未解决问题（或直接回想）
2. **选一个推进**：挑优先级最高的那个，用 `think` 想一下下一步能做什么
3. **行动**：如果需要查资料用 `web_search`，需要翻代码用 `read_file`/`grep_search`
4. **更新进展**：如果有了结论，用 `store_memory` 存下来；如果问题已解决，就标记完成

做完用 `rest` 结束。
