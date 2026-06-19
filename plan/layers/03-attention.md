# 注意力层 Attention Layer

## 一、目标

注意力层负责判断“当前大脑应该关注什么”。它根据输入事件、感知结果、已有 concerns、working set、drives 和情绪状态计算显著性分数。

## 二、边界

- 输入：`BrainEvent`、`PerceptionResult`、当前 state。
- 输出：`AttentionResult`。
- 不做记忆检索，不生成回复。
- 可以更新 `concerns`、`working_set` 和 `internal_state.attention`。

## 三、数据结构

```python
@dataclass
class AttentionResult:
    event_id: str
    focus: str
    focus_type: str             # entity / topic / event / none
    salience_map: dict[str, float]
    selected_reasons: list[str]
    suppressions: list[str] = field(default_factory=list)
```

## 四、评分模型

```text
salience =
  event.salience * 0.30
  + perception.salience_hint * 0.25
  + concern_effective * 0.20
  + drive_weight * 0.15
  + emotion_bias * 0.10
```

第一版允许使用简单权重，后续再从学习层反馈调整。

## 五、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| concerns 激活/衰减 | `backend/modules/brain/state/concerns.py` |
| working set | `backend/modules/brain/state/working_set.py` |
| drives | `backend/modules/brain/state/drives.py` |
| pending 表达生成 | `backend/modules/brain/state/pending_expression.py` |

## 六、流程

```text
PerceptionResult
  -> 收集候选 topic/entity
  -> 读取 concerns / drives / emotion
  -> 计算 salience_map
  -> 选择 focus
  -> 写入 working_set 和 internal_state.attention
```

## 七、文件清单

```text
backend/modules/brain/layers/attention/
  __init__.py
  result.py
  scorer.py
  focus.py
  updater.py
```

## 八、内部接口

```python
def score(event: BrainEvent, perception: PerceptionResult) -> AttentionResult
```

## 九、验收标准

1. 每次 chat 输入后能产生稳定的 `focus`。
2. 与记忆命中实体相关的输入会提升对应 concern。
3. salience 分数在 0 到 1 之间。
4. attention 层异常不影响 chat 回复。

## 十、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| ATT-001 | 定义 `AttentionResult` | PERC-001 | S |
| ATT-002 | 实现 salience scorer | ATT-001 | M |
| ATT-003 | 接入 concerns/working_set | ATT-002 | M |
| ATT-004 | 写入 `internal_state.attention` | ATT-003 | S |
| ATT-005 | 增加状态调试输出 | ATT-004 | S |
