# 记忆层 Memory Layer

## 一、目标

记忆层提供统一的短期、工作、长期、图谱记忆访问接口。第一阶段只包装现有模块，不重写、不移动 Qdrant、graph 和 memory pipeline。

## 二、边界

- 输入：`BrainEvent`、`PerceptionResult`、`AttentionResult`。
- 输出：`MemoryContext`。
- 不决定是否回复，不更新情绪。
- 通过 adapter 调用现有 `workmemory`、`search_memory`、`graph`。

## 三、数据结构

```python
@dataclass
class MemoryContext:
    event_id: str
    query: str
    working: dict
    semantic_hits: list[dict]
    graph_entities: list[str]
    associations: list[dict]
    memory_reference: str = ""
```

## 四、可复用现有能力

| 能力 | 现有位置 |
|---|---|
| 工作记忆 | `backend/modules/brain/memory/workmemory/` |
| 长期记忆检索 | `backend/modules/brain/memory/core.py` |
| Qdrant 检索 | `backend/modules/brain/memory/qdrant_search.py` |
| 图谱关联 | `backend/modules/brain/graph.py` |
| prompt 记忆注入 | `backend/modules/chat/pipeline/sections/memory.py` |
| 联想召回 | `backend/modules/chat/pipeline/sections/association_recall.py` |

## 五、流程

```text
AttentionResult.focus
  -> 生成记忆查询 query
  -> 调用 workmemory.handle_packagemem(query)
  -> 调用 search_memory(query)
  -> 调用 graph 关联实体和相关记忆
  -> build MemoryContext
```

## 六、文件清单

```text
backend/main_brain/memory/
  __init__.py
  context.py
  adapter.py
  recall.py
  association.py
```

## 七、内部接口

```python
def recall(event: BrainEvent, perception: PerceptionResult, attention: AttentionResult) -> MemoryContext
```

## 八、接入策略

1. 不改变 `backend/modules/brain/memory/` 现有代码位置。
2. 在 `backend/main_brain/memory/adapter.py` 中封装现有调用。
3. 后续如需替换底层存储，只改 adapter，不改上层流程。

## 九、验收标准

1. 同一个 chat 输入仍能触发现有语义记忆检索。
2. `MemoryContext.memory_reference` 能被 PromptPipeline 使用。
3. Qdrant 未就绪时返回空结果，不阻断主流程。
4. 记忆层耗时和错误在日志可见。

## 十、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| MEM-001 | 定义 `MemoryContext` | ATT-001 | S |
| MEM-002 | 实现 workmemory adapter | MEM-001 | S |
| MEM-003 | 实现 search adapter | MEM-001 | M |
| MEM-004 | 实现 graph association adapter | MEM-003 | M |
| MEM-005 | 接入 PromptContext 可选 memory_context | MEM-004 | M |
