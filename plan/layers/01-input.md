# 输入层抽象

## 一、项目目标

- **项目名称**：输入层抽象（Input Layer）
- **一句话描述**：main_brain 8 层架构的第 1 层。将当前单一的 `/chat/send` 输入抽象为统一的 `InputEvent` + `InputRouter` 体系，为未来多种输入源（屏幕视觉、剪贴板、文件变化、系统事件）铺路。
- **核心目标**：
  1. 定义标准 `InputEvent` 事件格式（source / type / modality / content / salience）
  2. 实现 `InputRouter.ingest(event)` 统一入口，对接现有 brain state
  3. 第一阶段只改造 chat 输入，不破坏现有逻辑
  4. 为未来输入源（eye_mcp 视觉、computer_mcp 环境）预留扩展点
- **不做的事**：
  - 不改变 chat 前端到后端的通信方式（仍是 SSE）
  - 不修改 LLM 调用链路
  - 不实现任何新输入源（只做抽象，不做具体接入）

## 二、业务背景

- **问题现状**：
  - 当前"输入层"就是 `/chat/send`，只接受文本字段
  - eye_mcp（屏幕截图）和 computer_mcp（剪贴板/文件/系统时间）已有 server 实现，但没有统一入口接入大脑
  - chat_routes.py 直接调 `ChatManager.send()`，没有"预处理→路由→分发"的环节
  - 系统缺少对"输入来自哪里"的感知

- **目标用户**：AiBrain 系统本身——输入层是大脑的感官入口

- **预期价值**：
  - 以后加"屏幕视觉输入"只需新增一个 source handler，不改 chat 链路
  - PromptContext 能知道"这次输入来自 chat / vision / system"，prompt 可以差异化
  - 输入事件统一落盘（input_events.jsonl），可追溯、可分析

## 三、功能需求

### P0（第一阶段）

| 功能 | 说明 |
|------|------|
| InputEvent 定义 | 标准事件格式：id/source/type/modality/content/timestamp/salience/metadata |
| InputRouter 骨架 | ingest(event) 统一入口，分发到 brain state |
| ChatSource 适配 | 把现有的 /chat/send 接入 InputEvent 体系 |
| 输入事件日志 | input_events.jsonl，append-only，自动截断 |

### P1（后续阶段）

| 功能 | 说明 |
|------|------|
| SystemSource | 定时 tick / 系统事件也作为输入接入 |
| VisionSource | eye_mcp 截图摘要作为视觉输入 |
| 多模态 PromptContext | PromptContext 可以拿到 input_event 元信息 |

## 四、非功能需求

- **兼容性**：第一阶段不改 chat 前端、不改 SSE 协议、不改 ChatManager.send() 签名
- **性能**：ingest() 处理 < 5ms（纯内存操作，不调 LLM）
- **可扩展**：新增输入源只需继承 BaseSource + register()
- **可观测**：input_events.jsonl 随时查看历史输入

## 五、系统架构

### 数据流（第一阶段改造后）

```
前端 POST /chat/send {message}
  → chat_routes.chat_send()
    → make_chat_event(message)        ← 新增：构造 InputEvent
    → router.ingest(event)            ← 新增：统一入口
        ├─ 写 input_events.jsonl
        ├─ 激活 working_set / concerns（可选）
        └─ 返回 event（原有链路继续）
    → mgr.send(event.content)         ← 不变：只传文本
```

### 目录结构（main_brain 整体规划）

```
backend/main_brain/
  input/              # 输入层（当前阶段）
    __init__.py
    event.py          # InputEvent dataclass
    router.py         # InputRouter.ingest()
    logger.py         # input_events.jsonl
    sources/
      __init__.py
      chat.py         # chat 文本 → InputEvent
      system.py       # (预留) 系统事件
      vision.py       # (预留) 视觉输入
  subconscious/       # 意识循环层（后续阶段）
    __init__.py
    loop.py
    emotion.py
    ...
```

### 现有文件改动（第一阶段）

| 文件 | 改动 |
|------|------|
| `backend/routes/chat_routes.py` | chat_send() 中新增一行 `router.ingest(event)` |
| `backend/modules/chat/loop.py` | send_message() 入参不变，只收 text |
| `backend/modules/chat/pipeline/context.py` | PromptContext 加 `input_event: InputEvent \| None` 字段 |
| `web/` | 不变 |

## 六、数据结构

### InputEvent

```python
@dataclass
class InputEvent:
    id: str                    # 唯一 ID，如 "inp_20260619_012345_abc123"
    source: str                # 输入源: "chat" | "system" | "vision" | "clipboard"
    type: str                  # 事件类型: "user_message" | "system_tick" | "screen_capture"
    modality: str              # 模态: "text" | "image" | "event"
    content: str               # 内容文本（chat 就是消息文本，vision 是视觉摘要）
    timestamp: str             # ISO 时间戳
    salience: float            # 0-1 显著性（chat 默认 0.8，system tick 默认 0.2）
    metadata: dict             # 扩展元信息（如 {window_title, language, region}）
```

### input_events.jsonl

```jsonl
{"id":"inp_abc","source":"chat","type":"user_message","modality":"text","content":"你好","timestamp":"2026-06-19T01:25:55","salience":0.8,"metadata":{}}
{"id":"inp_def","source":"system","type":"system_tick","modality":"event","content":"","timestamp":"2026-06-19T01:26:00","salience":0.2,"metadata":{}}
```

## 七、流程设计

### 核心流程：chat 输入接入 InputEvent

```
chat_routes.chat_send({message: "你好"})
  │
  ├─ 1. make_chat_event("你好")
  │     ├─ id = gen_id()
  │     ├─ source = "chat"
  │     ├─ type = "user_message"
  │     ├─ modality = "text"
  │     ├─ content = "你好"
  │     ├─ timestamp = now_iso()
  │     ├─ salience = 0.8
  │     └─ metadata = {}
  │
  ├─ 2. router.ingest(event)
  │     ├─ input_logger.write(event)    → input_events.jsonl 追加
  │     ├─ working_set.upsert(...)      → 激活输入中的实体（可选）
  │     └─ return event
  │
  └─ 3. mgr.send(event.content)         ← 原有链路完全不变
        → workmemory.input_mem_write    → loop.py → LLM
```

### 异常流程

- input_logger 写入失败：不阻塞 ingest，log warning
- source 未注册：默认按 chat 处理，不抛异常
- content 为空：仍构造 event 但 type="empty"，由 router 决定是否丢弃

## 八、API 设计

**无新增外部 HTTP API。** 只改内部调用链。

### 内部接口

```python
# input/__init__.py
def get_input_router() -> InputRouter

# router.py
class InputRouter:
    def ingest(self, event: InputEvent) -> InputEvent
    def register_source(self, name: str, handler: callable)

# event.py
@dataclass
class InputEvent: ...
def make_chat_event(text: str) -> InputEvent

# sources/chat.py
class ChatSource:
    def process(self, text: str) -> InputEvent
```

## 九、验收标准

| # | 验收项 | 预期 |
|---|--------|------|
| 1 | chat 输入产出 InputEvent | 发一条消息后，input_events.jsonl 有对应记录 |
| 2 | 原有 chat 功能不变 | 发送、接收、SSE 流式、记忆检索全部正常 |
| 3 | router.ingest 不阻塞 | 不影响 /chat/send 响应时间 |
| 4 | empty input 不报错 | 空消息仍能构造 event 不抛异常 |
| 5 | 模块可独立 import | `from modules.brain.input import get_input_router` 可用 |

## 十、开发任务拆分

| ID | 任务 | 依赖 | 复杂度 | 文件 |
|----|------|------|--------|------|
| T001 | 创建 input/ 模块骨架 + __init__.py | — | S | 新建 |
| T002 | 实现 InputEvent dataclass + make_chat_event() | — | S | `event.py` |
| T003 | 实现 InputRouter.ingest() | T001, T002 | S | `router.py` |
| T004 | 实现 input_events.jsonl 日志 | T002 | S | `logger.py` |
| T005 | 实现 ChatSource | T002 | S | `sources/chat.py` |
| T006 | 接入 chat_routes.py | T003, T005 | S | `chat_routes.py` |
| T007 | PromptContext 增加 input_event 字段 | T002 | S | `context.py` |
| T008 | 创建 sources/ 目录 + __init__.py | — | S | 新建 |
