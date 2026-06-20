# 表达与行动层 Expression / Action Layer

## 一、目标

表达层负责决定“说不说、说什么、以什么形式说”。它消费认知层的表达素材，并结合 pending、冷却、当前上下文输出 internal、seed 或 send 三种级别的结果。

本层封装现有 `pending_expression`、`expression_history` 和 `workmemory.output_mem_write`，不移动现有模块。

## 二、边界

- 输入：`CognitionResult`、`BrainStateSnapshot`。
- 输出：`ExpressionDecision`。
- 不负责发现关注点。
- 不改变前端 SSE 协议。

## 三、数据结构

```python
@dataclass
class ExpressionDecision:
    event_id: str
    level: str                 # internal / seed / send / suppress
    content: str
    target: str                # log / pending / chat / tool
    reason: str
    metadata: dict = field(default_factory=dict)
```

## 四、三级输出

| 级别 | 去向 | 用户可见 | 说明 |
|---|---|---|---|
| internal | `inner_monologue.jsonl` | 否 | 仅记录内心活动 |
| seed | pending queue | 否 | 等待冷却和优先级升级 |
| send | `output.json` 或 SSE | 是 | 主动表达或聊天回复 |
| suppress | 仅日志 | 否 | 被冷却、低价值或冲突抑制 |

## 五、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| pending 表达 | `backend/modules/brain/state/pending_expression.py` |
| 表达冷却 | `backend/modules/brain/state/expression_history.py` |
| output 写入 | `backend/modules/brain/memory/workmemory/workmemory.py` |
| chat SSE 回复 | `backend/modules/chat/loop.py` |

## 六、流程

```text
CognitionResult
  -> 判断表达价值
  -> 调用 expression_history adapter 检查 cooldown / refractory
  -> 选择 internal / seed / send / suppress
  -> 调用 pending_expression 或 output adapter 写入对应目标
```

## 七、文件清单

```text
backend/main_brain/expression/
  __init__.py
  decision.py
  monologue.py
  pending_adapter.py
  refractory_adapter.py
  output.py
  policy.py
```

## 八、内部接口

```python
def decide(ctx: BrainCycleContext) -> ExpressionDecision
def flush_pending(force: bool = False) -> int
```

## 九、验收标准

1. 现有 `pending_expression.py` 和 `expression_history.py` 位置不变。
2. 主动表达仍遵守现有冷却规则。
3. internal 级别不会出现在聊天窗口。
4. send 级别能写入 `output.json` 并被前端轮询看到。
5. 表达层失败不影响普通 chat 回复。

## 十、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| EXP-001 | 定义 `ExpressionDecision` | COG-001 | S |
| EXP-002 | 实现表达 policy | EXP-001 | M |
| EXP-003 | 封装 pending_expression adapter | EXP-002 | M |
| EXP-004 | 封装 expression_history adapter | EXP-002 | S |
| EXP-005 | 实现 inner monologue 日志 | EXP-001 | S |
