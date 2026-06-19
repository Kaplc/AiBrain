# 感知层 Perception Layer

## 一、目标

感知层负责把输入事件转换成结构化理解结果。它不做深度推理，只做轻量解析：意图、实体、情绪倾向、主题和重要性提示。

## 二、边界

- 输入：`BrainEvent`
- 输出：`PerceptionResult`
- 不直接调用重型 LLM，默认使用规则、关键词、已有图谱/实体工具。
- 不写长期记忆，只把结果交给 attention、memory、state 使用。

## 三、数据结构

```python
@dataclass
class PerceptionResult:
    event_id: str
    intent: str                 # greeting / question / command / chat / observe
    topics: list[str]
    entities: list[str]
    sentiment: str              # positive / neutral / negative
    sentiment_score: float      # -1.0 ~ 1.0
    urgency: float              # 0.0 ~ 1.0
    salience_hint: float        # 0.0 ~ 1.0
    metadata: dict = field(default_factory=dict)
```

## 四、可复用现有能力

| 能力 | 现有位置 | 用法 |
|---|---|---|
| 实体图谱 | `backend/modules/brain/graph.py` | 校验和规范化实体名 |
| 记忆结果实体 | `chat/pipeline/sections/association_recall.py` | 复用实体收集思路 |
| LLM 实体抽取 | `backend/modules/brain/llm.py` | P1 以后可作为可选增强 |

## 五、流程

```text
BrainEvent
  -> intent.classify(content)
  -> entity.extract(content)
  -> sentiment.score(content)
  -> topic.extract(content)
  -> build PerceptionResult
```

## 六、文件清单

```text
backend/modules/brain/layers/perception/
  __init__.py
  result.py
  intent.py
  entity.py
  sentiment.py
  topic.py
  analyzer.py
```

## 七、内部接口

```python
def analyze(event: BrainEvent) -> PerceptionResult
```

## 八、验收标准

1. chat 文本输入能生成 `intent`、`entities`、`sentiment`。
2. 空文本、超长文本、非文本事件不会抛异常。
3. 单次感知耗时目标小于 20ms，不包含可选 LLM 增强。
4. 输出能被 attention 层直接消费。

## 九、任务拆分

| ID | 任务 | 依赖 | 复杂度 |
|---|---|---|---|
| PERC-001 | 定义 `PerceptionResult` | `BrainEvent` | S |
| PERC-002 | 实现意图分类规则 | PERC-001 | S |
| PERC-003 | 实体抽取与图谱规范化 | PERC-001 | M |
| PERC-004 | 情绪倾向评分 | PERC-001 | S |
| PERC-005 | 统一 `analyze()` 编排 | PERC-002~004 | S |
