---
name: create_activity
description: 创建新活动并设为当前。action_detail=活动名（如 reflect），activity_context=描述做什么。结果：追加到活动列表，【长期活动】和【当前活动执行指引】会更新
terminates: false
---

# create_activity

创建一个新的活动目标，追加到活动列表并设为当前。

**结果**：新活动追加到活动列表并设为当前，`【长期活动】` 段会更新，`【当前活动执行指引】` 也会加载对应内容。

**不终止本轮**——创建后可以立即用 `use_tool` / `think` 开始做。

用法：
- `action_detail`：活动名（如 "reflect"、"self_learn"）
- `activity_context`：描述打算做什么、下一步计划

注意：想切换到已有的活动用 `set_activity`。
