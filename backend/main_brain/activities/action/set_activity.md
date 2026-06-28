---
name: set_activity
description: 切换到已有活动。action_detail=要切换的活动名（如 reflect），必须是已创建的。结果：当前活动切换，【长期活动】和【当前活动执行指引】会更新
terminates: false
---

# set_activity

切换到活动列表里的一个已有活动，把它设为当前焦点。

**结果**：当前活动切换为目标活动，`【长期活动】` 段的"当前"会更新，`【当前活动执行指引】` 也会加载对应内容。

**不终止本轮**——切过去后可以立即开始做。

用法：
- `action_detail`：要切换到的活动名（如 "reflect"、"self_learn"），必须是已存在的活动

注意：只能切换到已有的活动。如果想创建新活动用 `create_activity`。
