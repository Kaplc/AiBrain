# 大脑层总体路线图

## 一、目标

在现有 `backend/modules/brain`、`backend/modules/chat`、`mcp_servers` 的基础上，新建 `backend/main_brain/` 作为统一的大脑层。

`backend/main_brain/` 只负责统一协议、流程编排、adapter 接入和状态观测；现有模块保持原位，不迁移、不复制、不移动。

## 二、核心原则

1. 只接入，不迁移：`memory`、`state`、`chat`、`mcp_servers` 等现有模块保持原位。
2. 事件驱动：所有外部和内部刺激都统一为 `BrainEvent`。
3. adapter 包装：大脑层通过 adapter 调用现有模块，避免大面积改 import。
4. chat 只是输入源之一：`/chat/send` 保持原有行为，但进入大脑层时转换为 `source=chat` 的事件。
5. 可观测优先：每层都需要日志、最近状态和失败降级。

## 三、推荐目录

```text
backend/main_brain/
  __init__.py
  contracts.py              # BrainEvent、LayerResult、BrainCycleContext
  orchestrator.py           # 一次大脑循环的编排入口
  registry.py               # 层和 source 注册

  input/
  perception/
  attention/
  memory/                   # adapter：调用现有 modules/brain/memory
  state/                    # adapter：调用现有 modules/brain/state
  cognition/
  expression/               # adapter：调用现有 pending_expression / output
  learning/                 # adapter：调用现有 self_narrative / organizer / graph
```

配套实施说明：

```text
plan/layers/09-implementation-notes.md
```

## 四、统一数据契约

```python
@dataclass
class BrainEvent:
    id: str
    source: str              # chat / system / vision / clipboard / file / tool
    type: str                # user_message / tick / screen_snapshot / file_changed
    modality: str            # text / image / audio / event
    content: str
    timestamp: str
    salience: float = 0.0
    metadata: dict = field(default_factory=dict)
    raw: Any = None

@dataclass
class BrainCycleContext:
    event: BrainEvent
    perception: dict = field(default_factory=dict)
    attention: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    cognition: dict = field(default_factory=dict)
    expression: dict = field(default_factory=dict)
    learning: dict = field(default_factory=dict)
```

## 五、主流程

```text
BrainEvent
  -> Input.ingest
  -> Perception.analyze
  -> Attention.score
  -> Memory.recall          # 调用现有 memory 模块
  -> State.update           # 调用现有 state 模块
  -> Cognition.think
  -> Expression.decide      # 调用现有 pending/output 能力
  -> Learning.update        # 调用现有 reflection/organizer/graph 能力
```

chat 请求第一阶段链路：

```text
/chat/send
  -> make_chat_event(message)
  -> main_brain.orchestrator.process_event(event)
  -> ChatManager.send(event.content)
```

大脑层先参与记录、感知、状态激活，不替换原有 LLM 回复链路。

## 六、阶段规划

| 阶段 | 目标 | 主要产物 |
|---|---|---|
| P0 | 建立骨架和统一事件 | `contracts.py`、`orchestrator.py`、input 层接入 chat |
| P1 | 打通感知和注意力 | perception 轻量解析、attention salience、写入现有 state |
| P2 | 包装记忆和状态 | memory 只读 adapter、state adapter、状态 schema 版本升级 |
| P3 | PromptContext 上下文接入 | PromptContext 可选读取 brain_context，保留旧记忆路径 fallback |
| P4 | 认知和表达编排 | cognition result、expression decision、主动表达队列统一接入 |
| P5 | 学习闭环 | 对话后 lesson、记忆巩固、self narrative 更新接入 |
| P6 | 多输入源 | system tick、clipboard、vision、file watcher |

## 七、验收标准

1. 发送 chat 消息后，能在输入事件日志中看到 `source=chat` 的 `BrainEvent`。
2. 原有 chat SSE 回复、记忆检索、工作记忆写入不受影响。
3. `/chat/state` 或内部调试接口能看到最近一次事件、当前 focus、情绪/状态摘要。
4. 任意层失败只写日志，不阻断 chat 回复。
5. 新增输入源时不需要修改 chat 主链路。

## 八、实施约束

详细落地规则见 `09-implementation-notes.md`。第一版遵守以下约束：

1. 先观测、后影响：P0/P1 只记录事件、轻量感知、更新状态摘要，不接管回复。
2. 先旁路、后接管：`/chat/send` 的 SSE 和 `ChatManager.send()` 行为保持不变。
3. 先状态可见、后智能增强：每层必须暴露最近结果、耗时和错误，方便调试。
4. 避免重复记忆检索：现有 ChatLoop 已调用 `handle_packagemem()`，memory adapter 第一版只读和包装。
5. 表达层第一版不直接写 SSE，只允许 internal、seed、suppress，send 仍走现有主动表达链路。

