# LLM Agents 架构

## 一、项目目标

- **项目名称**：LLM Agents 架构（LLM Agents Architecture）
- **一句话描述**：在 `modules/LLM/Agents/` 下统一管理所有 LLM Agent，每个 Agent 是独立类，通过 `AgentManager` 单例对外提供服务，方便添加、删除、修改各类 Agent。
- **核心目标**：
  1. Agent 集中管理：所有 LLM 能力统一放在 `Agents/` 目录，不再散落在 `brain/llm.py`、`memory/events.py`、`memory/prompts.py` 中
  2. 单例访问：外部统一通过 `AgentManager.get_instance().get("agent_name")` 获取 Agent，调用 `.run()` 执行
  3. 即插即用：新增 Agent = 新建文件 + 一行注册，删除 Agent = 删文件 + 删注册行
  4. 向后兼容：`modules/brain/llm.py` 保留为兼容层，内部调 Agent，旧调用方零修改
- **不做的事**：
  - 不改造 `modules/LLM/` 底层的 stream/provider 分发
  - 不迁移 ConsciousnessLoop（chat 对话循环，带状态守护线程，不属于简单 Agent）
  - 不修改 PipelineEngine 和已有的流水线步骤（步骤调 Agent 是后续优化）

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| 功能散落 | `brain/llm.py` 有实体提取/关系推断/过滤/精炼；`memory/prompts.py` 有事件 prompt；`chat/prompts.py` 有对话 prompt | 新开发者找不到功能在哪 |
| 调用方式不统一 | 有的 `import extract_entities_llm`，有的 `import call_llm`，有的 `import get_event_store` | 心智负担高 |
| Prompt 与逻辑分离 | prompt 常量在 `prompts.py`，调用逻辑在 `events.py`，改 prompt 要改两个文件 | 维护成本高 |
| 无标准扩展流程 | 加一个新 LLM 功能不知道该放哪 | 开发效率低 |

### 2.2 目标用户

- **后端开发者**：需要添加/修改某个 LLM 调用功能时，知道去哪找、怎么加

### 2.3 预期价值

- 加一个新 Agent = 15 分钟（新建文件 + 一行注册）
- 所有 LLM 能力入口统一为 `AgentManager.get("xxx").run()`
- 每个 Agent 自包含 prompt + 逻辑 + 解析，不依赖外部文件

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| BaseAgent 基类 | 所有 Agent 继承统一基类，定义 `run()` 接口 | **P0** | 核心抽象 |
| AgentManager 单例 | 全局注册表，注册/获取/列举 Agent | **P0** | 类似 PipelineEngine 的单例模式 |
| 实体提取 Agent | 从文本中提取实体名和归属分类 | **P0** | 迁移 `brain/llm.extract_entities_llm` |
| 关系推断 Agent | 推断实体间关系类型（causal/similar/partof 等） | **P0** | 迁移 `brain/llm.infer_relations` |
| 记忆过滤 Agent | 按 query 相关性过滤候选记忆 | **P0** | 迁移 `brain/llm.filter_related_memories` |
| 记忆精炼 Agent | 合并多条相似记忆为一条精炼文本 | **P1** | 迁移 `brain/llm.refine_group` |
| 事件提取 Agent | 从记忆文本中提取结构化事件 | **P1** | 迁移 `memory/events.py` + `prompts.py` 中的事件提取逻辑 |
| 事件匹配 Agent | 根据 query 匹配相关事件 | **P1** | 迁移 `memory/events.py` 中的事件搜索逻辑 |
| 兼容层 | `brain/llm.py` 保留，内部改为调 Agent | **P0** | 旧调用方零修改 |

---

## 四、非功能需求

- **向后兼容**：`brain/llm.py` 的所有公开函数签名不变，内部改为调 AgentManager
- **可扩展**：新增 Agent = 新建文件继承 BaseAgent + 在 `Agents/__init__.py` 加一行 register
- **复用底层**：Agent 内部统一调 `LLMManager.get_instance().complete()` 发 LLM 请求，不直接调 stream
- **配置来源**：Agent 默认从 mem0_config 读取 provider/model/api_key，允许调用方通过 `run(..., config=LLMConfig)` 覆盖

---

## 五、系统架构

### 5.1 架构图

```
调用方（Pipeline Step / Route / 其他模块）
        │
        ▼
  AgentManager.get_instance().get("entity_extract")
        │
        ▼
  EntityExtractAgent.run(text)
        │
        ├── 用自己的 system_prompt（文件内常量）
        ├── LLMManager.get_instance().complete(sys_prompt, text, config)
        │       │
        │       ▼
        │   modules/LLM/stream.py → call_llm_stream → Provider API
        │
        └── 解析 LLM 响应 → 返回结构化 dict
```

### 5.2 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 基类 | Python ABC | BaseAgent 定义 `run()` 抽象方法 |
| AgentManager | 纯 Python 单例 | 内部 `dict[str, BaseAgent]` 注册表 |
| LLM 调用 | LLMManager.complete() | 复用现有模块，不直接调 openai SDK |
| 配置源 | mem0.json / LLMConfig | Agent 默认读 mem0_config，允许调用方覆盖 |

### 5.3 目录结构

```
backend/modules/LLM/
├── __init__.py              # [改] 导出 get_agent_manager
├── config.py                # [不改] LLMConfig dataclass
├── stream.py                # [不改] call_llm_stream / call_llm_sync
├── llm_mod.py               # [不改] LLMManager 单例
└── Agents/                  # [新增]
    ├── __init__.py          # [新增] AgentManager 单例 + register_all_agents()
    ├── base.py              # [新增] BaseAgent 抽象基类
    ├── entity_extract.py    # [新增] 实体提取 Agent
    ├── relation_infer.py    # [新增] 关系推断 Agent
    ├── memory_filter.py     # [新增] 记忆过滤 Agent
    ├── memory_refine.py     # [新增] 记忆精炼 Agent
    ├── event_extract.py     # [新增] 事件提取 Agent
    └── event_match.py       # [新增] 事件匹配 Agent

backend/modules/brain/
├── llm.py                   # [改] 兼容层，内部调 AgentManager
└── memory/
    ├── events.py            # [改] 事件提取/匹配调 Agent
    └── prompts.py           # [改] 已迁移的 prompt 标记弃用

backend/app.py               # [改] 增加 init_agents()
```

### 5.4 关键设计决策

1. **BaseAgent 最小接口**：只有一个 `run(input_data, **kwargs) → Any`。Agent 不是 Pipeline，不需要生命周期钩子
2. **Agent 自带 prompt**：每个 Agent 的 system_prompt 定义在自己文件内作为模块常量，不再引用外部的 `prompts.py`
3. **AgentManager 单例统管**：全局唯一 `AgentManager.get_instance()`，内部 `_registry: dict[str, BaseAgent]`。Agent 实例本身无状态，Manager 只负责根据 name 返回实例
4. **配置可覆盖**：Agent 默认从 `LLMConfig.from_mem0_config()` 加载配置；调用方可以传 `config=LLMConfig(...)` 覆盖
5. **兼容层不动旧代码**：`brain/llm.py` 保留所有函数签名，内部改为 `agent_manager.get("xxx").run(...)` 实现
6. **后台线程 Agent 特殊处理**：EventExtractAgent 是后台线程调用的 Agent，在 Agent 内部通过 `@staticmethod` 提供同步执行方法，线程中直接调

---

## 六、数据结构

### 6.1 BaseAgent 基类

```python
class BaseAgent(ABC):
    """Agent 基类 —— 所有 Agent 继承此接口"""

    name: str = ""               # 唯一标识（如 "entity_extract"）
    description: str = ""        # 人类可读描述
    system_prompt: str = ""      # 内置 system prompt（文件内常量）

    @abstractmethod
    def run(self, input_data: Any, **kwargs) -> Any:
        """执行 Agent

        Args:
            input_data: 主要输入（文本 / 列表 / dict）
            **kwargs:
                config: LLMConfig（可选，覆盖默认配置）
                temperature: float（可选）
                max_tokens: int（可选）

        Returns:
            结构化输出（dict / list / str）
        """
```

### 6.2 AgentManager 接口

```python
class AgentManager:
    """Agent 注册表单例"""

    _instance: 'AgentManager' = None
    _lock = threading.Lock()

    def __init__(self):
        self._registry: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """注册 Agent"""

    def get(self, name: str) -> BaseAgent:
        """获取 Agent，未注册抛 KeyError"""

    def list_agents(self) -> list[dict]:
        """返回所有 Agent 的 [{name, description}]"""

    def has(self, name: str) -> bool:
        """检查 Agent 是否已注册"""
```

### 6.3 Agent 注册表（初始）

| 注册名 | 类名 | 输入 | 输出 |
|--------|------|------|------|
| `entity_extract` | EntityExtractAgent | `text: str` | `{"entities": [...], "root": "用户"}` |
| `relation_infer` | RelationInferAgent | `entities: list, context: str` | `[{"from","to","relation_type","confidence"}]` |
| `memory_filter` | MemoryFilterAgent | `query: str, candidates: list` | `[related_id, ...]` |
| `refine` | RefineAgent | `memories: list[dict]` | `{"refined_text","category"}` |
| `event_extract` | EventExtractAgent | `memory_text: str` | `{"type":"event", "event":{...}}` 或 `{"type":"concept"}` |
| `event_match` | EventMatchAgent | `query: str, events: list` | `{"matched_indices": [...]}` |

---

## 七、流程设计

### 1. 添加新 Agent 流程

```
Step 1: 在 Agents/ 下新建文件 my_agent.py
Step 2: 继承 BaseAgent，实现 run()
Step 3: 在 Agents/__init__.py 中加一行 register()
Step 4: 外部调用 agent_manager.get("my_agent").run(...)
```

### 2. 删除 Agent 流程

```
Step 1: 删文件 my_agent.py
Step 2: 删 Agents/__init__.py 中的 register() 行
```

### 3. 迁移流程（以 EntityExtractAgent 为例）

```
改造前调用链：
  Pipeline Step → brain/llm.extract_entities_llm()
                → brain/llm._load_llm_config()
                → brain/llm.call_llm()
                → openai SDK

改造后调用链：
  Pipeline Step → brain/llm.extract_entities_llm()  ← 兼容层不变
                → agent_manager.get("entity_extract").run(text)
                → EntityExtractAgent.run()
                → LLMManager.get_instance().complete()
                → stream.call_llm_sync()
                → openai SDK
```

### 4. 异常处理

| 异常场景 | 处理方式 | 说明 |
|---------|---------|------|
| LLM 调用超时 | Agent 内部 try/except，记录 warn，返回默认空结果 | 不抛给调用方 |
| LLM 返回非 JSON | Agent 内部尝试容错解析（正则提取），失败返回默认值 | 兼容层 keep 旧行为 |
| Agent 未注册 | `AgentManager.get()` 抛 KeyError | 启动时注册检查确保不漏 |
| LLMConfig 无效 | Agent 内部校验，无效则使用默认配置 | 不中断执行 |

---

## 八、API 设计

### 8.1 AgentManager 调用

```python
from modules.LLM import get_agent_manager

mgr = get_agent_manager()

# 实体提取
result = mgr.get("entity_extract").run("志远帮我升级了记忆系统")
# → {"entities": ["志远", "记忆系统"], "root": "用户"}

# 关系推断（传额外参数）
result = mgr.get("relation_infer").run(
    input_data={"entities": ["志远", "猫猫"], "context": "志远帮猫猫升级了系统"},
    temperature=0.3,
)
# → [{"from": "志远", "to": "猫猫", "relation_type": "associated", "confidence": 0.9}]

# 过滤记忆（带自定义 config）
from modules.LLM import LLMConfig
cfg = LLMConfig(provider="deepseek", model="deepseek-chat", ...)
result = mgr.get("memory_filter").run(
    input_data={"query": "mem0", "candidates": [...]},
    config=cfg,
)

# 列举所有 Agent
agents = mgr.list_agents()
# → [{"name": "entity_extract", "description": "LLM 实体提取"}, ...]
```

### 8.2 兼容层（brain/llm.py）

```python
# 改造前
def extract_entities_llm(text: str) -> dict:
    cfg = _load_llm_config()
    raw = call_llm(ENTITY_EXTRACT_PROMPT, f"文本：{text}")
    return _parse_extract_response(raw)

# 改造后
def extract_entities_llm(text: str) -> dict:
    from modules.LLM import get_agent_manager
    return get_agent_manager().get("entity_extract").run(text)
```

调用方无感知。

### 8.3 init_agents() 启动点

在 `app.py` 中 `init_pipelines()` 之后调用：

```python
def _init_agents():
    from modules.LLM.Agents import register_all_agents
    register_all_agents()
    logger.info("AgentManager initialized")

# create_app() 中调用顺序：
# 1. warmup_memory()
# 2. init_pipelines()
# 3. _init_agents()       ← 新增
# 4. 注册路由
```

---

## 九、验收标准

### 9.1 功能验收

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|---------|
| A1 | AgentManager 注册 | `list_agents()` | 返回 6 个 Agent 的 name+description |
| A2 | 实体提取 Agent | `get("entity_extract").run("志远升级")` | 返回包含"志远"的 entities 列表 |
| A3 | 兼容层不变 | 调 `brain/llm.extract_entities_llm("志远升级")` | 结果与 A2 一致 |
| A4 | 关系推断 Agent | 传 entities+context | 返回带 relation_type 的数组 |
| A5 | 记忆过滤 Agent | 传 query + 候选列表 | 返回排好的相关 ID |
| A6 | 记忆精炼 Agent | 传多条相似记忆 | 返回合并后的精炼文本 |
| A7 | 事件提取 Agent | 传包含事件的文本 | 返回结构化事件对象 |
| A8 | 事件匹配 Agent | 传 query + 事件列表 | 返回匹配索引 |
| A9 | 旧 store/search 正常 | 执行 memory store/search | 结果与改造前一致 |
| A10 | 新增 Agent | 新建文件 + 一行注册 | 立即通过 `get()` 可用 |

### 9.2 交付物清单

- [ ] `modules/LLM/Agents/__init__.py` — AgentManager 单例 + register_all_agents()
- [ ] `modules/LLM/Agents/base.py` — BaseAgent 抽象基类
- [ ] `modules/LLM/Agents/entity_extract.py` — 实体提取 Agent
- [ ] `modules/LLM/Agents/relation_infer.py` — 关系推断 Agent
- [ ] `modules/LLM/Agents/memory_filter.py` — 记忆过滤 Agent
- [ ] `modules/LLM/Agents/memory_refine.py` — 记忆精炼 Agent
- [ ] `modules/LLM/Agents/event_extract.py` — 事件提取 Agent
- [ ] `modules/LLM/Agents/event_match.py` — 事件匹配 Agent
- [ ] `modules/LLM/__init__.py` — [改] 导出 get_agent_manager
- [ ] `modules/brain/llm.py` — [改] 兼容层调 Agent
- [ ] `modules/brain/memory/events.py` — [改] 事件逻辑调 Agent
- [ ] `modules/brain/memory/prompts.py` — [改] 已迁移 prompt 标记弃用
- [ ] `app.py` — [改] 增加 init_agents()

---

## 十、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 预估代码量 | 所属模块 |
|---------|----------|------|--------|-----------|---------|
| T001 | BaseAgent 基类定义 | 无 | S | ~30 行 | Agents/base.py |
| T002 | AgentManager 单例（register/get/list/has） | T001 | S | ~60 行 | Agents/__init__.py |
| T003 | EntityExtractAgent（brain/llm.py → Agent） | T002 | S | ~60 行 | Agents/entity_extract.py |
| T004 | RelationInferAgent（brain/llm.py → Agent） | T002 | S | ~70 行 | Agents/relation_infer.py |
| T005 | MemoryFilterAgent（brain/llm.py → Agent） | T002 | M | ~80 行 | Agents/memory_filter.py |
| T006 | RefineAgent（brain/llm.py → Agent） | T002 | M | ~70 行 | Agents/memory_refine.py |
| T007 | EventExtractAgent（memory/events.py prompts → Agent） | T002 | M | ~80 行 | Agents/event_extract.py |
| T008 | EventMatchAgent（memory/events.py prompts → Agent） | T002 | M | ~70 行 | Agents/event_match.py |
| T009 | brain/llm.py 兼容层（内部调 Agent） | T003-T006 | M | ~40 行 | brain/llm.py |
| T010 | memory/events.py 改造（调 Agent） | T007, T008 | M | ~30 行 | memory/events.py |
| T011 | memory/prompts.py 清理已迁移 prompt | T007, T008 | S | ~10 行 | memory/prompts.py |
| T012 | app.py + LLM/__init__.py 集成 | T002 | S | ~8 行 | app.py, LLM/__init__.py |

**并行分组**：
- 组1（基础设施）：T001 → T002（串行）
- 组2（Agent 迁移）：T003、T004、T005、T006、T007、T008（可并行，均依赖 T002）
- 组3（兼容层）：T009 依赖组2，T010 依赖 T007/T008，T011 依赖 T007/T008
- 组4（集成）：T012 依赖 T002

**预估工作量**：约 6-8 小时，~600 行代码
