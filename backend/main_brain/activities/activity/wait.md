---
name: wait
description: 安静等待——无值得做的事，更新 idle/energy 后休眠
handler_name: wait
tick_types: [short_tick, medium_tick, long_tick]
autonomy_min: observe
max_cycles: 0
allowed_tools: []
conditions: {}
---

# 等待活动（AI 执行指引）

什么都不做，安静待着。没有值得做的事时直接 `rest` 就好。
不需要调用任何工具，不需要思考，安静休息即可。
