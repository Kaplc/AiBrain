# Chat Agent 原生工具调用

## 一、项目目标

- **项目名称**：Chat Agent 原生工具调用（Chat Tool Calling）
- **一句话描述**：在 Chat Tab 的对话中让 LLM 能主动调用 memory_search、memory_store 等工具获取或写入信息，无需经过 MCP。
- **核心目标**：
  1. LLM 在对话中可主动调工具（第一期：memory_search、memory_store）
  2. 工具调用过程全非流式（简单可靠），最终文本直接返回
  3. 前端展示每次工具调用的名称、参数、结果
  4. 后端完全自包含，不依赖 MCP 代码
- **不做的事**：
  - wiki 搜索不纳入第一期（后续再看）
  - 不替代 brain_mcp（MCP 通道保留给 AI 编码助手）
  - 不做动态工具加载（工具代码注册）
  - 不做工具调用权限分级（全量可用）
  - 不改造现有 Chat 的纯文本路径（`tools_enabled=False` 时行为完全不变）

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| LLM 被动 | 只能根据注入的记忆上下文回答，不能主动搜索 | 回答靠"猜"而不是查 |
| 无法写入 | 对话中想"记住这个"只能手动复制到 Memory Tab | 交互割裂，用户需要切换页面 |
| 上下文丢失 | `_conversation_history` 只存最终文本，tool_calls 和结果跨轮丢失 | 用户追问"展开第一条"时 LLM 不知道第一条是什么 |
| 无工具视角 | Chat 用户看不到 LLM"思考过程"中的信息检索 | 对话黑盒，信任感低 |

### 2.2 目标场景

```
场景1：用户问"帮我查一下关于 XX 的记忆"
  → LLM 调 memory_search("XX")
  → 基于结果组织回答

场景2：用户说"记住：张三的生日是 5 月 20 号"
  → LLM 调 memory_store("张三的生日是 5 月 20 号")
  → 确认已记住
```

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| ToolRegistry | 作为 LLM，我希望系统提供可调用的工具列表以便我按需使用 | **P0** | 注册表单例 |
| memory_search | 作为 LLM，我希望语义搜索长期记忆以便回答用户问题 | **P0** | 封装 search_memory() |
| memory_store | 作为 LLM，我希望保存新信息到长期记忆以便未来回忆 | **P0** | 封装 store_memory() |
| Tool Loop | LLM 调工具后自动循环直到返回文本，上限 8 轮 | **P0** | 非流式调 LLM |
| 前端工具展示 | 作为用户，我希望看到 LLM 调了哪些工具和结果 | **P0** | ToolCallDisplay 组件 |
| 工具执行结果追加 | 工具执行结果以 tool role 追加到 messages，供 LLM 继续推理 | **P0** | OpenAI tool 消息格式 |

---

## 四、非功能需求

| 指标 | 要求 |
|------|------|
| 响应时间 | Tool Loop 内单轮 LLM 调用等待 ≤ 30s |
| 稳定性 | Tool Loop 超 8 轮自动终止，不卡死 |
| 兼容性 | 支持 OpenAI 兼容 + Anthropic 两类 provider |
| 向后兼容 | `tools_enabled=False` 时行为与现有完全一致 |

---

## 五、系统架构

### 5.1 架构图

```
routes/chat_routes.py
        ↓
modules/chat/loop.py — send_message()
        │
        ├─ tools_enabled=False → 直接 LLM stream（现有逻辑，不变）
        │
        └─ tools_enabled=True → Tool Loop:
               ┌─ 非流式 LLM (带 tools schemas)
               ├─ 有 tool_calls → 执行 → 追加 tool result → 循环
               └─ 无 tool_calls → 取 content → yield 给前端

        ↓
modules/LLM/stream.py — 新增 tools / tool_choice 参数
        ↓
modules/LLM/config.py — 不变
```

### 5.2 技术栈

| 组件 | 技术 | 理由 |
|------|------|------|
| 工具注册表 | 纯 Python 单例 | 简单，无外部依赖 |
| LLM 调用 | OpenAI / Anthropic SDK | 已有，只需加 tools 参数 |
| 前端展示 | Vue 3 组件 | 复用现有技术栈 |

### 5.3 目录结构

```
backend/modules/chat/
├── __init__.py
├── chat_mod.py          ← 新增 tools_enabled 配置
├── loop.py              ← 修改：Tool Loop 核心逻辑
├── prompts.py
├── agent_loop.py
├── pipeline/
└── tools/               ← 新目录
    ├── __init__.py
    ├── registry.py      ← ToolRegistry 单例
    └── memory_tools.py  ← memory_search, memory_store

web/src/views/chat/
├── ChatView.vue         ← 修改：解析 tool_history 事件
└── components/
    └── ToolCallDisplay.vue  ← 新建
```

### 5.4 关键设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| Tool Loop 非流式 | 全程非流式调 LLM，最终文本直接 yield | 避免流式拼装 tool_calls delta 的复杂度 |
| 冗余 LLM 调用 | 最后一轮非流式响应的 content 即为最终回答，无需再调一次流式 | 省钱，省延迟 |
| 多轮上下文 | `_conversation_history` 保存 tool loop **完整消息链**（含 tool_calls + tool results），而非只存最终文本 | 下一轮用户追问时 LLM 能看到上一轮的工具调用过程 |
| 前端展示方式 | SSE 事件 `tool_history` 一次性下发全部工具链 | 非流式工具调用结束后整批发送 |
| 并行工具调用 | `parallel_tool_calls=True` | LLM 可一次返回多个 tool_calls，减少轮次 |

---

## 六、数据结构

### 6.1 ToolDef

```python
@dataclass
class ToolDef:
    name: str                               # 工具名，如 "memory_search"
    description: str                        # LLM 理解的含义
    parameters: dict                        # OpenAI JSON schema
    fn: Callable                            # 执行函数
    enabled: bool = True
```

### 6.2 SSE 协议扩展

```json
{"type": "tool_history", "tools": [
    {"name": "memory_search", "arguments": {"query": "..."}, "result": "..."}
]}
{"type": "token", "content": "最终回复文本..."}
{"type": "done"}
```

无新增数据库表。

---

## 七、流程设计

### 7.1 Tool Loop 流程

```
用户消息 → send_message()
    │
    ├─ 写入工作记忆 input.md
    ├─ 触发 package 记忆搜索
    ├─ PromptPipeline 构造 system prompt
    ├─ 构建 messages 数组（从 _conversation_history 读取历史）
    │
    └─ tools_enabled=True?
         │
         ├─ 是 → Tool Loop:
         │      loop (最多 8 轮):
         │        1. 非流式调 LLM (messages + tools schemas)
         │        2. 判 finish_reason:
         │           ├─ "tool_calls" → 遍历 tool_calls:
         │           │   ├─ 执行 registry.execute(name, args)
         │           │   ├─ 记录 tool_history
         │           │   └─ 追加 {"role":"tool", ...} 到 messages
         │           │   → 继续下一轮
         │           └─ "stop" → 取 content 作为 final_text → 退出循环
         │        3. 超 8 轮 → final_text = 兜底消息 → 退出
         │
         │  tool loop 结束后，将完整消息链（含 tool_calls + tool results）追加到 _conversation_history
         │  （而非只存 user/assistant 最终文本）
         │
         └─ 否 → 现有纯文本流程
               └─ LLM stream → yield token → done
               └─ 追加 user + assistant 到 _conversation_history（现有逻辑，不变）
    │
    └─ yield tool_history
    └─ yield token (final_text)
    └─ yield done
```

### 7.2 异常处理

| 场景 | 处理 |
|------|------|
| LLM 返回无效 tool_calls | 跳过该轮，继续循环 |
| 工具执行抛异常 | 捕获异常，将错误信息作为 tool result 返回给 LLM |
| 超出 8 轮 | 终止循环，返回兜底消息 |
| API 密钥缺失 | 现有 503 逻辑不变，不进入 Tool Loop |

---

## 八、API 设计

无新增 API 端点。Chat SSE 协议扩展：

### `/chat/send` — SSE 事件新增

现有事件：`start`, `token`, `usage`, `done`, `error`

新增事件：

**`tool_history`** — 在 `token` 之前发送

```
data: {"type": "tool_history", "tools": [
    {"name": "memory_search", "arguments": {"query": "XX"}, "result": "[...]"},
    {"name": "memory_store",  "arguments": {"text": "YY"}, "result": "已记住"}
]}
```

---

## 九、验收标准

### 功能验收

1. Chat 输入"帮我查一下关于 XX 的记忆" → LLM 调 `memory_search` → 基于结果回复
2. Chat 输入"记住：XX" → LLM 调 `memory_store` → 回复确认
3. 前端展示每次工具调用的名称、参数、结果（可折叠展开）
4. 工具调用超过 8 轮 → 终止并显示提示

### 兼容性验收

5. `tools_enabled=False` 时行为与现有完全一致（回归测试）
6. 不开启任何工具时（空注册表），Tool Loop 退化为纯文本回复

### 边界验收

7. 工具执行抛异常 → LLM 收到错误信息 → 继续推理或回复用户
8. 多个 tool_calls 并行执行 → 全部执行后再喂回 LLM

---

## 十、开发任务拆分

| ID | 任务 | 依赖 | 复杂度 | 模块 | 对应需求 |
|----|------|------|--------|------|---------|
| T001 | 创建 `tools/` 目录 + `registry.py`（ToolRegistry 单例） | — | S | chat/tools | 功能需求 |
| T002 | 实现 `memory_tools.py`（memory_search, memory_store） | T001 | S | chat/tools | 功能需求 |
| T003 | `stream.py` 新增 `call_llm_nonstream()` 和 tools/tool_choice 参数 | — | M | LLM | 功能需求 |
| T004 | `loop.py` 新增 Tool Loop 逻辑（含完整消息链存 `_conversation_history`） | T001, T003 | M | chat | 功能需求 |
| T005 | `chat_routes.py` SSE 增加 `tool_history` 事件 | T004 | S | routes | 功能需求 |
| T006 | `app.py` 注册所有工具 | T002 | S | app | 功能需求 |
| T007 | 新建 `ToolCallDisplay.vue` 组件 | — | M | web | 前端展示 |
| T008 | 修改 `ChatView.vue` 解析 `tool_history` 事件 | T005, T007 | S | web | 前端展示 |
| T009 | 手工回归测试 + 修复 | T001-T008 | M | — | 验收 |

依赖关系：T001→T002→T006，T003 独立，T004 依赖 T001+T003，T008 依赖 T005+T007，T009 依赖全部。
