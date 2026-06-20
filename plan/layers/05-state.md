# 状态层 State Layer

## 一、目标

状态层负责维护大脑的内部状态视图，包括 self model、drives、concerns、working set、open loops、pending expressions、emotion、attention 和最近输入摘要。

本层通过 state adapter 调用现有 `backend/modules/brain/state/*`，不迁移、不复制现有 Manager。

## 二、边界

- 输入：前面各层的结构化结果。
- 输出：`BrainStateSnapshot`。
- 负责统一读写状态视图和补充新字段。
- 不直接做 LLM 推理，不生成回复。

## 三、数据结构

```python
@dataclass
class BrainStateSnapshot:
    emotion: dict
    attention: dict
    sensory: dict
    concerns: list[dict]
    working_set: list[dict]
    open_loops: list[dict]
    goals: list[dict]
    pending: list[dict]
```

建议在现有 internal state 中补充：

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

## 四、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| InternalState 事务 | `backend/modules/brain/state/store.py` |
| concerns | `backend/modules/brain/state/concerns.py` |
| working_set | `backend/modules/brain/state/working_set.py` |
| open_loops | `backend/modules/brain/state/open_loops.py` |
| drives | `backend/modules/brain/state/drives.py` |
| pending_expression | `backend/modules/brain/state/pending_expression.py` |
| self_model | `backend/modules/brain/state/self_model.py` |

## 五、流程

```text
Layer Results
  -> update sensory
  -> update emotion drift and mood label
  -> update attention focus
  -> call concerns / working_set / open_loops adapters
  -> build BrainStateSnapshot
```

## 六、文件清单

```text
backend/main_brain/state/
  __init__.py
  snapshot.py
  adapter.py              # 调用现有 modules/brain/state/*
  emotion.py
  updater.py
```

## 七、内部接口

```python
def update_context(ctx: BrainCycleContext) -> BrainStateSnapshot
def get_snapshot() -> BrainStateSnapshot
```

## 八、验收标准

1. 现有 `modules/brain/state/*` 文件位置不变。
2. `internal_state.json` 缺字段时能自动补默认值。
3. 每次 chat 输入后 `sensory.last_event_id` 更新。
4. attention focus 能落盘并被 `/chat/state` 读取。
5. state 文件损坏时能降级恢复默认结构。

## 九、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| STATE-001 | 实现 state adapter | ATT-004 | S |
| STATE-002 | 定义 `BrainStateSnapshot` | STATE-001 | S |
| STATE-003 | 实现 emotion 轻量漂移 | STATE-001 | M |
| STATE-004 | 实现 state updater | STATE-002 | M |
| STATE-005 | 扩展 `/chat/state` 返回摘要 | STATE-004 | S |
