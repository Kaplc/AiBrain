"""Activity / Action Definition System — 双层活动定义包

action/    — 原子动作定义：由 _get_action_descriptions() 读取，注入 AI prompt 的「你可以做的事」
activity/  — 高层活动指引：由 _get_activity_suggestions() 读取，注入 AI prompt 的「参考活动」
              AI 自建活动也会被 _write_activity_md() 写入此目录，与系统活动同一通道。
"""
