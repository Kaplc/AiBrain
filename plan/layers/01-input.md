# 输入层 Input Layer

## 一、目标

输入层是大脑层的第一层，负责把 chat、系统 tick、视觉、剪贴板、文件变化等刺激统一封装为 `BrainEvent`。

第一阶段只接入现有 `/chat/send`，不改变前端、不改变 SSE、不改变 `ChatManager.send()` 的主链路。

## 二、边界

- 输入：现有来源传入的原始数据，例如 chat 文本。
- 输出：`BrainEvent`。
- 不做深度理解，那是感知层职责。
- 不调用 LLM。
- 不迁移现有 chat 模块，只在路由入口旁路接入大脑层。

## 三、数据结构

```python
@dataclass
class BrainEvent:
    id: str
    source: str                # chat / system / vision / clipboard / file
    type: str                  # user_message / system_tick / screen_capture
    modality: str              # text / image / event
    content: str
    timestamp: str
    salience: float
    metadata: dict = field(default_factory=dict)
    raw: Any = None
```

## 四、第一阶段流程

```text
POST /chat/send {message}
  -> chat_routes.chat_send()
  -> make_chat_event(message)
  -> input_router.ingest(event)
      -> append input_events.jsonl
      -> 记录最近输入状态
      -> 返回 event
  -> mgr.send(event.content)
```

## 五、推荐文件

```text
backend/main_brain/input/
  __init__.py
  event.py
  router.py
  event_log.py
  sources/
    __init__.py
    chat.py
    system.py       # 预留
    vision.py       # 预留
```

## 六、接入点

| 文件 | 改动 |
|---|---|
| `backend/routes/chat_routes.py` | 在调用 `mgr.send()` 前构造并 ingest `BrainEvent` |
| `backend/main_brain/input/*` | 新增输入层实现 |
| `backend/modules/chat/pipeline/context.py` | 后续可选增加 `brain_context`，第一阶段不强制 |

## 七、内部接口

```python
def make_chat_event(text: str, metadata: dict | None = None) -> BrainEvent

def get_input_router() -> InputRouter

class InputRouter:
    def ingest(self, event: BrainEvent) -> BrainEvent: ...
```

## 八、验收标准

1. 发送 chat 消息后，`input_events.jsonl` 有对应事件。
2. 原有 chat 回复、SSE 流、记忆检索全部正常。
3. 输入层异常只写 warning，不阻断 `/chat/send`。
4. 新输入源只需要新增 source adapter。

## 九、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| INPUT-001 | 定义 `BrainEvent` | 无 | S |
| INPUT-002 | 实现 `make_chat_event()` | INPUT-001 | S |
| INPUT-003 | 实现 `InputRouter.ingest()` | INPUT-001 | S |
| INPUT-004 | 实现 `input_events.jsonl` 追加日志 | INPUT-001 | S |
| INPUT-005 | 在 `chat_routes.py` 接入 | INPUT-002~004 | S |
