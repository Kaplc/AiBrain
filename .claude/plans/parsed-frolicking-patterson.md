# 添加企微主动推送 Agent 工具

## Context

用户希望让 AI Agent（BrainJudge）能够通过 `use_tool` action 主动向企业微信用户推送消息。当前 `WeWorkBot.send_proactive()` 底层能力已实现，但未注册为 Tool，BrainJudge 无法调用。

## 改动文件

### 1. 新增：`backend/modules/LLM/tools/wework_tools.py`

参照 `memory_tools.py` 的模式，定义：

- **`_wework_send_fn(userid, content, msgtype="markdown")`**
  - 检查 `WeWorkBot` 是否已配置且已连接，未连接返回友好提示
  - 调用 `WeWorkBot.get_instance().send_proactive(userid, content, msgtype)`
  - 返回执行结果字符串（成功/失败）
- **`WEWORK_SEND_TOOL = ToolDef(name="wework_send", ...)`**
  - `description`: 明确说明"向企业微信用户主动推送消息"
  - `parameters`: userid（必填）, content（必填）, msgtype（可选，默认 markdown）
- **`register_wework_tools()`**: 注册工具到 ToolRegistry

### 2. 修改：`backend/app.py` (第 417 行附近)

在 `_preload()` 的工具注册块中新增：

```python
try:
    from modules.LLM.tools.wework_tools import register_wework_tools
    register_wework_tools()
except Exception as e:
    logger.warning(f"wework_tools failed: {e}")
```

### 3. 修改：`backend/main_brain/adapters/tools.py` (第 15 行)

将 `"wework_send"` 加入默认白名单：

```python
DEFAULT_WHITELIST = ["memory_search", "web_fetch", "wework_send"]
```

这样 BrainJudge 在 reactive session 和后台 tick 中都能通过 `use_tool` action 调用它。

## 调用链路

```
BrainJudge (LLM)
  → next_action: "use_tool"
  → action_args: {"name": "wework_send", "args": {"userid": "...", "content": "..."}}
  → ToolAdapter.handle_use_tool()
    → ToolAdapter.call("wework_send", args)
      → ToolRegistry.execute("wework_send", args)
        → _wework_send_fn(userid, content)
          → WeWorkBot.get_instance().send_proactive()
```

## 注意事项

- `send_proactive` 的前提是目标用户之前已在企微中给机器人发过至少一条消息（企业微信平台限制），工具的描述中需说明
- `WeWorkBot` 未连接或未配置时，工具应返回清晰的错误提示而非 crash
- 该工具有写权限（能发送消息），加入白名单后需用户确认是否接受此风险；可通过 `brain.json['tool_whitelist']` 运行时移除

## 验证

1. 启动后端，检查日志中是否出现 `wework_tools registered` 或未报错
2. 通过 `get_tool_registry().get_all_tools()` 确认 `wework_send` 已注册
3. 在企微连接状态下，让 BrainJudge 在 reactive 对话中触发 `wework_send` 工具调用
4. 或直接通过 `/gate/proactive` HTTP 路由测试底层 `send_proactive` 是否正常
