"""
上下文压缩配置

修改此文件即可调整压缩行为。
修改后需重启后端生效。
"""

# 上下文最大 Token 数（近似模型上下文窗口大小）
MAX_CONTEXT_TOKENS = 4000

# 压缩触发比例（实际 prompt_tokens / MAX_CONTEXT_TOKENS 超过此值时触发压缩）
COMPRESS_TRIGGER_RATIO = 0.7
