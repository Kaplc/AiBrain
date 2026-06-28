"""Activity / Action Definition System — 双层活动定义包

action/    — 原子动作定义（5 个）：think / use_tool / create_activity / speak / rest
              每个 tick 只能选一个 action 执行，use_tool 会继续循环，其余终止。
activity/  — 高层活动指引（13 个）：reflect / self_learn / chat_learn / update_goals / ……
              跨多次 tick 的目标，由 AI 用多个 action 组合完成。

registry.py 递归扫描所有子目录。autonomous_mind 从 activity/ 提取活动建议给 AI 选。
"""
