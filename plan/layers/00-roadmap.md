# 大脑层总体路线图

在现有 `backend/modules/brain`、`backend/modules/chat`、`mcp_servers` 的基础上，建设一个统一的大脑层，用来承接输入、感知、注意力、记忆、状态、认知、表达和学习更新。

第一阶段不搬迁现有核心能力，而是在 `backend/modules/brain/layers/` 下建立统一协议和编排入口。现有模块继续作为能力提供者，逐步由大脑层包装和调度。

## 核心原则

1. 先编排，后迁移：不要一开始把 `memory/`、`state/` 大量搬目录，先用 adapter 包装现有能力。
2. 事件驱动：所有外部和内部刺激都统一为 `BrainEvent`。
3. 层间只传结构化结果：每层输出 dataclass/dict，不直接依赖上层实现。
4. chat 只是输入源之一：`/chat/send` 保持原有行为，但进入大脑层时转换为 `source=chat` 的事件。
5. 可观测优先：每层都需要日志、最近状态和失败降级。

## 推荐目录

```text
backend/modules/brain/layers/
  __init__.py
  contracts.py
  orchestrator.py
  registry.py
  input/
  perception/
  attention/
  memory/
  state/
  cognition/
  expression/
  learning/
```

暂不建议使用 `backend/main_brain/`，因为当前项目已有 `backend/modules/brain/`，继续放在这里能减少 import 路径分裂。

## 统一数据契约

```python
@dataclass
class BrainEvent:
    id: str
    source: str
    type: str
    modality: str
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

## 主流程

```text
BrainEvent
  -> Input.ingest
  -> Perception.analyze
  -> Attention.score
  -> Memory.recall
  -> State.update
  -> Cognition.think
  -> Expression.decide
  -> Learning.update
```

## 阶段规划

| 阶段 | 目标 | 主要产物 |
|---|---|---|
| P0 | 建立骨架和统一事件 | `contracts.py`、`orchestrator.py`、input 层接入 chat |
| P1 | 打通感知和注意力 | perception 轻量解析、attention salience、写入 state |
| P2 | 包装记忆和状态 | memory adapter、state snapshot、PromptContext 可读取事件上下文 |
| P3 | 认知和表达编排 | cognition result、expression decision、主动表达队列统一 |
| P4 | 学习闭环 | 对话后 lesson、记忆巩固、self narrative 更新 |
| P5 | 多输入源 | system tick、clipboard、vision、file watcher |

## 验收标准

1. 发送 chat 消息后，能在输入事件日志中看到 `source=chat` 的 `BrainEvent`。
2. 原有 chat SSE 回复、记忆检索、工作记忆写入不受影响。
3. `/chat/state` 或内部调试接口能看到最近一次事件、当前 focus、情绪/状态摘要。
4. 任意层失败只写日志，不阻断 chat 回复。
5. 新增输入源时不需要修改 chat 主链路。
