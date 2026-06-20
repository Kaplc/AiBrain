# 学习更新层 Learning / Update Layer

## 一、目标

学习层负责在一次交互或后台循环之后更新系统经验：对话 lesson、记忆巩固、图谱边权、自我叙事和策略反馈。

本层调用现有 self_narrative、organizer、graph、memory pipeline 能力，不移动现有模块。

## 二、边界

- 输入：完整 `BrainCycleContext`、聊天结果、工具结果。
- 输出：`LearningUpdate`。
- 不阻塞用户回复，默认后台执行。
- 不做重量级全量重建，除非用户手动触发。

## 三、数据结构

```python
@dataclass
class LearningUpdate:
    event_id: str
    lessons: list[str]
    memory_updates: list[dict]
    graph_updates: list[dict]
    narrative_updates: list[dict]
    errors: list[str] = field(default_factory=list)
```

## 四、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| 记忆存储/检索 | `backend/modules/brain/memory/core.py` |
| 记忆 pipeline | `backend/modules/brain/memory/pipeline/` |
| self narrative reflection | `backend/modules/brain/memory/self_narrative/reflection.py` |
| 图谱关系 | `backend/modules/brain/graph.py` |
| 去重整理 | `backend/modules/brain/organizer.py` |

## 五、更新频率

| 更新类型 | 触发 | 是否 LLM | 说明 |
|---|---|---|---|
| lesson 提取 | 每轮 chat 完成后 | 可选 | 从 user/assistant 对中抽取经验 |
| 图谱 co-activation | 每轮有实体时 | 否 | 强化共同出现实体 |
| 记忆巩固 | 定时或手动 | 可选 | dedup / organize |
| self narrative | 每日或重大事件 | 是 | 更新自我叙事 |
| 策略反馈 | 表达后 | 否 | 记录表达是否被打断、是否继续对话 |

## 六、流程

```text
BrainCycleContext + response
  -> 提取 lesson candidates
  -> 判断是否值得入库
  -> 调用 graph adapter 更新 co-activation
  -> 必要时调用 self_narrative reflection
  -> 记录 LearningUpdate
```

## 七、文件清单

```text
backend/main_brain/learning/
  __init__.py
  update.py
  lesson.py
  consolidation_adapter.py
  graph_adapter.py
  narrative_adapter.py
```

## 八、内部接口

```python
def update_after_chat(ctx: BrainCycleContext, assistant_text: str) -> LearningUpdate
def tick() -> LearningUpdate
```

## 九、验收标准

1. 现有 self_narrative、organizer、graph 模块位置不变。
2. 普通 chat 回复完成后，学习层后台执行不阻塞 SSE。
3. LLM 不可用时 lesson 提取跳过但不报错。
4. 有实体共现时 graph 权重可增量更新。
5. 每次更新都有可查日志。

## 十、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| LEARN-001 | 定义 `LearningUpdate` | COG-001 | S |
| LEARN-002 | 实现 chat 后台学习入口 | LEARN-001 | M |
| LEARN-003 | 实现 lesson 提取策略 | LEARN-002 | M |
| LEARN-004 | 实现 graph adapter | LEARN-002 | M |
| LEARN-005 | 接入 self narrative reflection adapter | LEARN-003 | M |
