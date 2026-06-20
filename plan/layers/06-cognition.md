# 认知层 Cognition Layer

## 一、目标

认知层负责“想什么”和“接下来可能做什么”。它接收注意力焦点、记忆上下文和内部状态，生成推理摘要、预测、目标更新和表达素材。

本层接入现有 open_loops、goals、pending 能力，不移动现有模块。

## 二、边界

- 输入：`AttentionResult`、`MemoryContext`、`BrainStateSnapshot`。
- 输出：`CognitionResult`。
- 不直接写 `output.json`。
- 不直接替代 chat LLM 回复，第一阶段只作为上下文补充。

## 三、数据结构

```python
@dataclass
class CognitionResult:
    event_id: str
    thought_summary: str
    predictions: list[dict]
    open_loop_updates: list[dict]
    goal_updates: list[dict]
    expression_seed: str = ""
    confidence: float = 0.5
```

## 四、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| pending 扫描 | `backend/modules/brain/state/pending_expression.py` |
| open loops | `backend/modules/brain/state/open_loops.py` |
| goals | `backend/modules/brain/state/goals.py` |
| PromptPipeline | `backend/modules/chat/pipeline/` |
| LLM Agents | `backend/modules/LLM/Agents/` |

## 五、流程

```text
attention.focus + memory_context + state_snapshot
  -> 轻量推理：当前焦点意味着什么
  -> 预测：下一步可能需要什么
  -> 通过 adapter 更新 open loops / goals
  -> 生成 expression_seed
```

## 六、文件清单

```text
backend/main_brain/cognition/
  __init__.py
  result.py
  reasoning.py
  prediction.py
  goals_adapter.py
  open_loops_adapter.py
  planner.py
```

## 七、内部接口

```python
def think(ctx: BrainCycleContext) -> CognitionResult
```

## 八、验收标准

1. 有 attention focus 时能生成 `thought_summary`。
2. 现有 open_loops、goals、pending 模块位置不变。
3. 认知层输出不会直接污染聊天历史。
4. LLM 不可用时仍能生成空/规则结果。
5. `expression_seed` 能被表达层消费。

## 九、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| COG-001 | 定义 `CognitionResult` | MEM-001, STATE-002 | S |
| COG-002 | 实现规则推理摘要 | COG-001 | M |
| COG-003 | 接入 open_loop adapter | COG-002 | M |
| COG-004 | 接入 goals adapter | COG-002 | M |
| COG-005 | 输出 expression seed | COG-003 | S |
