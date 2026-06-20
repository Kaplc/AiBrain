# 大脑层实施补充说明

## 一、目标

本文补充 `00-roadmap.md` 到 `08-learning.md` 中缺少的落地约束，重点保证第一版大脑层可观测、可回滚、不会破坏现有 chat SSE、记忆检索和主动表达链路。

核心策略：

```text
先观测 -> 后影响
先旁路 -> 后接管
先状态可见 -> 后智能增强
```

## 二、第一版接入边界

### chat 链路

现有 `/chat/send` 仍保持主链路：

```text
/chat/send
  -> ChatManager.send(user_msg)
  -> modules.chat.loop.send_message()
  -> PromptPipeline
  -> LLM SSE
```

大脑层只做旁路观察：

```text
/chat/send
  -> make_chat_event(user_msg)
  -> main_brain.orchestrator.process_event(event, mode="observe")
  -> ChatManager.send(user_msg)
```

约束：

1. 不改变前端 SSE 协议。
2. 不改变 `ChatManager.send()` 的参数和返回事件格式。
3. 大脑层异常只能写 warning，不允许中断 `/chat/send`。
4. 大脑层耗时逻辑不能插入 token streaming 中间。

## 三、Orchestrator 模式

建议 `process_event()` 支持 mode，避免一开始就全链路执行：

```python
def process_event(event: BrainEvent, mode: str = "observe") -> BrainCycleContext:
    ...
```

| mode | 用途 | 执行层 |
|---|---|---|
| `observe` | chat 第一阶段旁路 | input、perception、attention、state |
| `full_cycle` | 后续完整大脑循环 | input 到 expression |
| `background_tick` | 后台学习和主动表达 | state、cognition、expression、learning |
| `dry_run` | 调试和测试 | 不落盘或只写临时日志 |

第一阶段 `/chat/send` 只使用 `observe`。

## 四、统一层结果

每层除了业务结果，建议统一包装运行状态，便于 `/chat/state` 或调试接口查看。

```python
@dataclass
class LayerRun:
    name: str
    ok: bool
    skipped: bool = False
    latency_ms: float = 0.0
    error: str = ""
    result: dict = field(default_factory=dict)
```

`BrainCycleContext` 可以增加：

```python
layer_runs: dict[str, LayerRun] = field(default_factory=dict)
```

验收要求：

1. 每层失败不抛出到 chat 路由。
2. 每层记录 `latency_ms`。
3. 最近一次 cycle 的 `last_error` 可在状态接口看到。

## 五、日志与文件路径

建议日志放在项目已有日志目录下，避免散落到模块目录。

```text
logs/main_brain/
  input_events.jsonl
  cycle_events.jsonl
  layer_errors.log
  inner_monologue.jsonl
```

事件日志最小字段：

```json
{
  "id": "evt_xxx",
  "source": "chat",
  "type": "user_message",
  "modality": "text",
  "content_preview": "前 120 字",
  "timestamp": "2026-06-20T01:00:00+08:00",
  "salience": 0.4,
  "metadata": {}
}
```

注意：日志里保存 `content_preview` 即可，完整原文是否保存由后续隐私策略决定。

## 六、State Schema 升级

现有 `backend/modules/brain/state/store.py` 使用 `CURRENT_VERSION = 5`。新增大脑层字段时，建议升级到 v6，并在默认状态中补齐：

```json
{
  "sensory": {
    "last_event_id": "",
    "last_user_message_at": "",
    "idle_seconds": 0
  },
  "emotion": {
    "valence": 0.0,
    "arousal": 0.3,
    "dominance": 0.5,
    "mood_label": "neutral",
    "last_update_at": ""
  },
  "attention": {
    "focus": "",
    "focus_type": "",
    "salience_map": {},
    "last_shift_at": ""
  },
  "layers": {
    "last_cycle_at": "",
    "last_error": "",
    "tick_counts": {}
  }
}
```

迁移约束：

1. 只补缺失字段，不覆盖用户已有状态。
2. state 文件损坏时仍走现有默认恢复逻辑。
3. adapter 写状态必须走 `InternalState.transaction()`。

## 七、Memory 去重策略

现有 ChatLoop 已在对话开始时调用：

```text
workmemory.handle_packagemem(query=prompt)
PromptPipeline(memory section)
```

因此 P2 的 memory adapter 第一版只做只读包装：

```text
读取 work_memory
读取已存在 package results
包装为 MemoryContext
记录耗时和错误
```

第一版不要再次同步调用重型检索，避免：

1. 重复 Qdrant 查询。
2. 重复更新 package memory。
3. 增加首 token 延迟。

等 P3 接入 `PromptContext.brain_context` 后，再决定是否把记忆检索统一迁移到大脑层。

## 八、PromptContext 接入策略

P3 才允许修改 `backend/modules/chat/pipeline/context.py`，新增可选字段：

```python
brain_context: dict = field(default_factory=dict)
```

约束：

1. 旧的 `work_memory` 路径保留。
2. 新 section 必须可开关。
3. `brain_context` 缺失时 PromptPipeline 输出不变。
4. 如果大脑层失败，PromptPipeline 自动 fallback 到旧逻辑。

## 九、Expression 限制

Expression 第一版不直接写 SSE。

允许：

| level | 允许状态 | 去向 |
|---|---|---|
| `internal` | 允许 | `inner_monologue.jsonl` |
| `seed` | 允许 | pending queue |
| `suppress` | 允许 | 日志 |
| `send` | 暂不开放 | 仍交给现有 proactive 链路 |

原因：

1. 普通 chat 回复已经由 `ChatManager.send()` 负责。
2. 主动表达已有 `pending_expression.proactive_send()` 和冷却规则。
3. 直接写 SSE 容易造成普通回复和主动表达混流。

## 十、Learning 后台化

Learning 层默认不能阻塞用户回复。

第一版建议顺序：

1. 对话完成后记录 `LearningUpdate` 空壳和事件引用。
2. 有实体共现时做 graph co-activation。
3. lesson 提取作为可选后台任务。
4. self narrative reflection 只在定时或手动触发时执行。

约束：

1. LLM 不可用时跳过 lesson，不报错到用户。
2. 后台任务要有独立日志。
3. 不做全量记忆重建，除非用户手动触发。

## 十一、推荐验收顺序

| 阶段 | 验收 |
|---|---|
| P0 | `/chat/send` 后出现 `logs/main_brain/input_events.jsonl` |
| P1 | `/chat/state` 能看到 `sensory.last_event_id` 和 `attention.focus` |
| P2 | `MemoryContext` 能包装现有 work memory，且不重复检索 |
| P3 | PromptPipeline 可选读取 `brain_context`，关闭后行为不变 |
| P4 | internal monologue 和 pending seed 可查，SSE 不受影响 |
| P5 | learning 后台日志可查，失败不影响 chat |

## 十二、实现红线

1. 不迁移 `backend/modules/brain/*`。
2. 不复制现有 memory/state manager。
3. 不改变 `/chat/send` SSE 事件格式。
4. 不在 token streaming 中做重型 LLM 或重型检索。
5. 不让大脑层异常冒泡到用户聊天请求。
