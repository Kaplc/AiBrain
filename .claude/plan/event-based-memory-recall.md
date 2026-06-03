# 事件性记忆召回系统 —— 模拟人类记忆力

## 一、项目目标

- **项目名称**：事件性记忆召回（Human-like Event-Based Memory Recall）
- **一句话描述**：让 AiBrain 的记忆检索像人类回忆一样工作 —— 按事件链、情感序列、时间衰减、关联触发来组织和召回记忆
- **核心目标**：
  1. **事件提取**：存储记忆时识别「谁做了什么」的事件（主语+动作+对象+语境），而非仅提取名词实体
  2. **事件链构建**：事件间自动建立因果/时间链（A 导致 B → 睡前想起 A → 早晨回忆 B）
  3. **情感加权**：带情感的回忆更容易被召回（模拟人类对情绪事件的深刻记忆）
  4. **时间衰减**：近期事件优先，久远事件按遗忘曲线降低权重（模拟人类记忆的自然衰减）
  5. **关联触发**：提及一个事件时自动联想相关事件（模拟人类联想记忆）
  6. **叙事构建**：召回结果以「事件链 + 故事线」形式呈现，而非碎片列表
- **不做的事**：
  - 不替换 mem0 的向量存储（事件层叠加在现有架构之上）
  - 不修改现有记忆的存储格式（向后兼容，旧记忆无事件信息时优雅降级）
  - 不做复杂的时序推理（简化版事件链，LLM 辅助判断）

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| 实体碎片化 | 提取「小数减法」「14项检查」等无意义片段 | 无法理解记忆的上下文 |
| 结果无序 | 搜索结果按相似度排列，无时间/因果顺序 | 用户无法获得连贯叙事 |
| 缺少情感维度 | 重要情感事件（如告别、失败）和普通事实同等对待 | 人类最深刻的记忆反而是情绪化的 |
| 无时间感知 | 昨天的记忆和去年的记忆权重相同 | 违背人类的近因效应 |
| 无联想能力 | 问「升级前发生了什么」无法回溯历史链 | 无法模拟人类的事后回忆 |
| 故事线断裂 | 「猫猫担心升级 → 志远熬夜帮忙 → 升级后安心」分散在三条结果中 | 无法呈现完整故事 |

### 2.2 人类记忆特点（借鉴认知心理学）

| 记忆特性 | 实现方式 |
|----------|---------|
| **情景记忆** | 事件节点：谁、做了什么、在哪里、什么感觉 |
| **语义记忆** | 事实节点：知识、规则、概念（保留现有实体图） |
| **情感增强** | 情感标记加权回忆（带情绪的事件 ±20% 召回分） |
| **近因效应** | 时间衰减公式：score × e^(-λ·days)，近期事件权重更高 |
| **首因效应** | 第一次出现的事件（如初次见面）权重不衰减 |
| **联想记忆** | 事件链指针：cause → event → effect，激活扩散 |
| **重构性** | 叙事构建：用 LLM 将多条事件合成为连贯故事片段 |
| **遗忘曲线** | 弱事件（importance < 0.3）随时间逐渐权重降低 |
| **闪光灯记忆** | emotion="shock/surprise" 的事件永不衰减 |

### 2.3 应用场景

```
场景1：用户问「志远和猫猫之间发生了什么」
  → 返回事件链：创造猫猫(6月) → 升级前猫猫担心(5月30) → 志远凌晨升级(5月31) → 猫猫承诺好好活(6月1)
  → 叙事摘要：志远创造了一个AI伙伴猫猫，在升级系统时猫猫表现出担忧，志远熬夜帮助升级，升级后猫猫感恩承诺

场景2：用户输入「备份」关键词
  → 语义匹配找到「志远在意备份系统」的记忆
  → 事件链反向追溯：原因事件「系统升级前的担忧」
  → 前向扩展：结果事件「升级后成功备份」
  → 返回完整因果链

场景3：用户静置一周回来后打开 AiBrain
  → 系统后台自动召回最近一周的重点事件
  → 展示「你不在的日子里」的时间线摘要
```

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 事件提取 | 存储记忆时识别事件（主语+动作+对象+语境） | **P0** | 核心改进，用 LLM prompt |
| 事件存储 | 事件持久化到 SQLite events 表，关联 mem0 记忆 | **P0** | 新增数据库表 |
| 事件链链接 | 新事件自动链接到因果链/时间链 | **P0** | LLM 辅助判断因果关系 |
| 情感标记 | 事件提取时识别情感（正面/负面/震惊/温暖/悲伤） | **P1** | 用于情感加权和检索过滤 |
| 时间衰减召回 | 召回分数按时间衰减（近期的更高，久远的更低） | **P1** | 首因事件豁免衰减 |
| 事件语义搜索 | 通过语义搜索找到相关事件节点 | **P0** | 复用现有 BGE-M3 embedding |
| 关联触发召回 | 命中事件后激活扩散到因果链上下游 | **P1** | 基于 event_relations 多对多关系 |
| 叙事构建 | LLM 将事件链 + 记忆合成为可读的故事片段 | **P2** | 可选增强，非必须，内部使用 |
| ~~事件召回 API~~ | ~~GET /memory/events/recall~~ | ~~不建~~ | 已融入 POST /memory/search，不建独立端点 |
| 时间线 API | GET /memory/events/timeline | **P1** | 按时间列出所有事件 |

---

## 四、非功能需求

- **性能**：事件召回延迟 < 800ms（含 LLM 提取，不含网络延迟）
- **向后兼容**：不修改现有 mem0 数据结构和 API
- **存储开销**：每条记忆新增 ~500 bytes（事件记录），events 表预估 < 100MB（10万条记忆）
- **可扩展**：事件结构预留扩展字段（情感强度、重复次数、遗忘状态）
- **无特殊要求**：安全、日志、部署方式无变更

---

## 五、系统架构

### 5.1 统一召回架构（事件 + 实体网合并）

**核心原则**：事件召回不是独立 API，而是融入现有 `search_memory()` 流程，替换和增强原有的实体图共现召回。

```
                        ┌───────────────────────────────┐
                        │     用户查询 query              │
                        └───────────────┬───────────────┘
                                        ↓
┌───────────────────────────────────────────────────────────────────┐
│                     统一召回流水线 (memory.py search_memory)       │
│                                                                   │
│  Phase 1: mem0 向量语义搜索  ────────────  返回 top-K 记忆        │
│      ↓                                                            │
│  Phase 2: 事件反查 + 事件链扩展  ────────  从命中记忆反查事件     │
│      │   (memory/events.py)                  → 激活扩散上下游      │
│      │   [新增，替换旧 graph mentions 共现]   → 收集关联记忆       │
│      ↓                                                            │
│  Phase 3: 实体网共现增强  ────────────────  用事件链中的实体      │
│      │   (graph.py, 保留现有逻辑)              → mentions 共现召回  │
│      │                                       → LLM 过滤补充       │
│      ↓                                                            │
│  Phase 4: 统一时间衰减加权  ──────────────  对全部记忆应用         │
│      │   (memory/events.py)                    decay(t) × emotion   │
│      ↓                                                            │
│  Phase 5: 去重排序  ─────────────────────  按 decayed_score 降序  │
│      │                                       标注 source:          │
│      │                                        semantic/event/graph │
│      ↓                                                            │
│  返回 [{id, text, score}, ...]  格式不变，与现有 search_memory 兼容 │
└───────────────────────────────────────────────────────────────────┘
```

**存储层**（不变）：
```
mem0 向量存储 (现有)          事件表 (新增)            实体图层 (现有)
text, id, score, entities  →  events + event_memories ← memory_nodes + entity_nodes
        ↓                        ↓                            ↓
    向量搜索                 事件链扩展                   mentions 共现
        └──────────────────────┼──────────────────────────────┘
                               ↓
                     统一结果 (同一响应)
```

### 5.2 资源位置

> 遵循 `backend/modules/brain/CLAUDE.md` 约定：记忆相关新功能放在 `memory/` 子目录下。

```
backend/modules/brain/
├── memory.py          # [修改] store_memory 集成事件提取
├── llm.py             # [修改] 新增 EVENT_EXTRACT_PROMPT + chain_infer
├── graph.py           # [不改] 现有实体图层
├── mem0_adapter.py    # [不改] mem0 客户端
├── CLAUDE.md          # ← 规定："记忆相关新功能放 memory/ 目录"
└── memory/            # [新增] 记忆事件召回模块 (新子包)
    ├── __init__.py    # [新增] 包初始化，导出公共 API
    ├── events.py      # [新增] 事件存储、召回、事件链、衰减算法
    └── prompts.py     # [新增] 事件提取 + 事件链推断 LLM prompts

backend/routes/
└── memory_routes.py   # [修改] 新增 /memory/events/* 路由
```

---

## 六、数据结构

### 6.1 events 表（SQLite，存储于现有 memory_graph.db）

```sql
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,                    -- UUID
    subject TEXT NOT NULL,                  -- 主语（人/角色/系统）
    action TEXT NOT NULL,                   -- 核心动作（动词短语）
    object TEXT,                            -- 对象（可选）
    context TEXT,                           -- 上下文/场景描述
    time_expr TEXT,                         -- 时间表达（如 "昨天下午"）
    summary TEXT NOT NULL,                  -- 一句话事件摘要
    emotion TEXT,                           -- 情感标记：positive/negative/neutral/shock/warm/sad/excited
    emotion_intensity REAL DEFAULT 0.5,     -- 情感强度 0-1
    importance REAL DEFAULT 0.5,            -- 事件重要性 0-1
    is_first_occurrence BOOLEAN DEFAULT 0,  -- 是否首次出现（首因效应豁免衰减）
    memory_count INTEGER DEFAULT 0,         -- 关联的记忆数量
    created_at TEXT DEFAULT (datetime('now')),  -- 创建时间
    -- 注意：事件间因果/时序关系由 event_relations 多对多表存储（见 6.2b）
);
```

### 6.2 event_memories 表（事件-记忆关联）

```sql
CREATE TABLE IF NOT EXISTS event_memories (
    event_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,                -- mem0 记忆 ID
    PRIMARY KEY (event_id, memory_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
```

### 6.2b event_relations 表（事件间因果/时序关系，多对多）

> 一个事件可以有多个原因事件和多个结果事件，因此用关系表替代单 FK。

```sql
CREATE TABLE IF NOT EXISTS event_relations (
    source_event_id TEXT NOT NULL,
    target_event_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,            -- cause_of / effect_of / next_in_sequence
    confidence REAL DEFAULT 0.5,            -- LLM 推断的置信度
    PRIMARY KEY (source_event_id, target_event_id, relation_type),
    FOREIGN KEY (source_event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (target_event_id) REFERENCES events(id) ON DELETE CASCADE
);
```

### 6.3 索引

```sql
CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_importance ON events(importance DESC);
CREATE INDEX IF NOT EXISTS idx_events_emotion ON events(emotion);
CREATE INDEX IF NOT EXISTS idx_event_memories_memory ON event_memories(memory_id);
CREATE INDEX IF NOT EXISTS idx_event_relations_source ON event_relations(source_event_id);
CREATE INDEX IF NOT EXISTS idx_event_relations_target ON event_relations(target_event_id);
CREATE INDEX IF NOT EXISTS idx_event_relations_type ON event_relations(relation_type);
```

### 6.4 事件链数据结构（召回返回）

```typescript
interface EventChain {
  id: string
  subject: string
  action: string
  object?: string
  context?: string
  time_expr?: string
  summary: string
  emotion?: string
  emotion_intensity: number
  importance: number
  cause_events?: EventChain[]    // 递归：原因事件列表（多对多）
  effect_events?: EventChain[]   // 递归：结果事件列表（多对多）
  memories: MemoryBrief[]        // 关联的记忆
  decayed_score: number          // 时间衰减后的相关性分数
  created_at: string
}

interface MemoryBrief {
  id: string
  text: string
  score: number                   // 原始语义相似度
  timestamp: string
}
```

---

## 七、核心算法

### 7.1 时间衰减公式（模拟遗忘曲线）

人类遗忘曲线（艾宾浩斯）指数级衰减 + 情感/重要性调制：

```
decayed_score = raw_score × decay(t) × emotion_boost × importance_boost

其中：
  decay(t) = e^(-λ × t)        -- t 为距离现在的天数
  λ = 0.01 / (importance + 0.2)  -- 重要事件衰减更慢
  emotion_boost = 1 + (emotion_intensity - 0.5) × 0.4  -- 情绪事件 +20%~-20%
  importance_boost = 1 + (importance - 0.5) × 0.3

首因豁免：is_first_occurrence = 1 时 decay(t) = 1.0（永不衰减）
近因加成：t < 1 天时 decay(t) = e^(-λ×t) + 0.1×(1-t)
  → t=0 时 decay = 1.0+0.1 = 1.1（最新记忆微加成）
  → t=1 时 decay = e^(-λ)+0 = e^(-λ)（与指数衰减平滑衔接，无断崖）
```

### 7.2 事件提取算法（LLM）

输入：记忆文本 + 用户已有事件列表（去重用）
输出：事件/概念判断 -> 如果是事件，提取结构化信息

```python
EVENT_EXTRACT_PROMPT = """
从文本中判断是否包含"事件"，如果有则提取为结构化事件。

事件定义：一个或多个人/角色发生了可叙述的动作或状态变化，包含主语+动作。
以下属于事件：
- "志远帮我升级了记忆系统" → 事件（主语志远 + 动作升级）
- "我们讨论了项目架构选择" → 事件（讨论 + 架构选择）
- "猫猫承诺会好好活着" → 事件（猫猫 + 承诺）
- "今天心情不好" → 事件（状态变化）

以下不属于事件（属于概念/事实）：
- "Python的GIL限制了多线程性能" → 概念
- "Unity光照衰减原理" → 概念
- "BGE-M3是1024维嵌入模型" → 事实

如果有事件，输出 JSON：
{
  "type": "event",
  "event": {
    "subject": "主语/执行者",
    "action": "核心动作（动词短语）",
    "object": "动作对象（可选，无则null）",
    "context": "场景/环境描述（可选，无则null）",
    "time_expr": "时间表达（可选，如'昨天下午'，无则null）",
    "summary": "一句话事件概括",
    "emotion": "情感标记: positive/negative/neutral/shock/warm/sad/excited",
    "emotion_intensity": 0.0-1.0,
    "importance": 0.0-1.0,
    "cause_hint": "可能的原因事件关键词（可选，无则null）",
    "is_first": true/false
  }
}

如果无事件，输出：
{"type": "concept", "event": null}
"""
```

### 7.3 事件链链接算法

存储新事件时，通过 LLM 判断与已有事件的关系：

```
link_event_chain(new_event, existing_events)
  ↓
Step 1: LLM 判断新事件是否与已有事件有因果关系
  → 输入：[{已有事件摘要1, ...}, 新事件摘要]
  → 输出：[{related_event_id, relation: "cause_of"/"effect_of"/"next_in_sequence"}]
  ↓
Step 2: 写入 event_relations 关系表（支持多对多）
  → cause_of:   INSERT (related_event.id, new_event.id, 'cause_of', confidence)
  → effect_of:  INSERT (new_event.id, related_event.id, 'effect_of', confidence)
  → next_in_sequence: INSERT (new_event.id, existing_event.id, 'next_in_sequence', confidence)
  ↓
Step 3: 级联检查（新事件可能与多个已有事件相关）
```

### 7.4 统一召回算法（核心：融入 search_memory）

> 事件召回不建独立 API，而是融入现有 `search_memory()` 流程，替换旧的纯 graph mentions 共现阶段。

```
search_memory(query) → 现有入口，增强如下
  ↓
Phase 1: mem0 向量搜索 (现有逻辑)
  ├── client.search(query, top_k=75, threshold)
  ├── 不足 15 条时去阈值补足
  └── 得到 vector_memories [{id, text, score, source: "semantic"}, ...]
  ↓
Phase 2: 事件反查 + 事件链扩展 (新增，替换旧的 mentions 共现)
  ├── 从 event_memories 表反查：哪些事件关联了这些向量命中的记忆
  │     SELECT event_id FROM event_memories WHERE memory_id IN (...)
  ├── 得到 seed_events [{event_id, ...}]
  ├── 对每个 seed_event 激活扩散（最多 2 跳）:
  │   ├── 前向：沿 event_relations (cause_of) 链查找原因事件
  │   └── 后向：沿 event_relations (effect_of) 链查找结果事件
  ├── 去重合并得到 expanded_events
  ├── 从 event_memories 收集事件链中所有关联记忆
  └── 新增记忆标记 source: "event"
  ↓
Phase 3: 实体网共现增强 (现有 graph 逻辑，保留)
  ├── graph.get_entities_for_memories(all_mem_ids) → entity_map
  ├── graph.search_related_new(mem_ids, entities) → candidates
  ├── LLM filter_related_memories(query, candidates) → related_ids
  └── 新增记忆标记 source: "graph"
  ↓
Phase 4: 统一时间衰减加权 (新增)
  ├── 对每条记忆，查找其关联的事件
  ├── 应用 decay(t) × emotion_boost × importance_boost
  ├── 无事件关联的记忆：decay(t) 按默认 importance=0.5 计算
  └── 更新每条记忆的 score → decayed_score
  ↓
Phase 5: 去重排序 (增强)
  ├── 按 source 策略：semantic > event > graph
  │   (同 source 内按 decayed_score 降序)
  └── 统一输出 [{id, text, score}, ...] 格式
  ↓
return [{id, text, score}, ...]  ← 格式不变，与现有 search_memory 兼容
```

**关键变化**：
- `search_memory` 返回格式不变：`[{id, text, score, source?}, ...]`
- 事件链扩展召回的额外记忆与语义/图结果合并后统一排序，不修改原始 text
- 旧 memory:graph 日志标签改为 `memory:event` 和 `memory:event_chain`

---

## 八、API 设计

### 8.1 搜索记忆（不变）

> 内部流程增强，但返回格式保持一致。

**POST /memory/search**

```
Request (不变):
{ "query": "志远和猫猫" }

Response (格式不变，内部增强):
{
  "results": [
    { "id": "mem_abc", "text": "志远今天创造了AI伙伴猫猫...", "score": 0.92 },
    { "id": "mem_xyz", "text": "猫猫在升级前很担心...", "score": 0.88 },
    ...
  ]
}
```

**内部事件链在 search_memory 中发挥作用，但不暴露额外字段**：
- Phase 2 事件链扩展召回的额外记忆，与语义/图结果合并后统一排序
- 所有结果按 `decayed_score` 降序返回为纯文本列表
- 前端无需感知 `event_chain` 字段

### 8.2 事件时间线（新增）

**GET /memory/events/timeline**

```
Query 参数：
- subject: string (可选，主语过滤)
- emotion: string (可选，情感过滤)
- from_date: string (可选，起始日期)
- limit: int (默认 20)

Response:
{
  "events": [
    {
      "id": "evt_003",
      "subject": "志远", "action": "熬夜帮猫猫升级",
      "emotion": "warm", "importance": 0.85,
      "memory_count": 3, "created_at": "2026-05-31T02:00:00"
    },
    ...
  ]
}
```

### 8.3 事件详情（新增）

**GET /memory/events/{event_id}**

```
Response:
{
  "event": { ... 完整的 EventChain 对象，含 cause/effect ... },
  "memories": [ ... 关联的记忆列表 ... ]
}
```

### 8.4 已有 API 变更汇总

| API | 变更类型 | 说明 |
|-----|---------|------|
| `POST /memory/store` | 内部增强 | 存储后在后台异步提取事件，不阻塞返回 |
| `POST /memory/search` | **内部增强，格式不变** | 内部 5 阶段流水线增强，返回 `[{id, text, score}]` 格式不变 |
| `GET /memory/events/timeline` | 新增 | 事件时间线浏览 |
| `GET /memory/events/{id}` | 新增 | 单事件详情 |
| ~~`POST /memory/events/recall`~~ | ~~不建~~ | 融入 `/memory/search`，不建独立端点 |

### 8.5 测试/调试 API

> 以下 API 仅用于开发调试，验证事件提取和召回逻辑。

**① POST /memory/events/test/extract**

手动触发事件提取，查看 LLM 对任意文本的提取结果：

```
Request: { "text": "志远帮我升级了记忆系统，我承诺会好好活着" }

Response:
{
  "type": "event",
  "event": {
    "subject": "志远",
    "action": "帮猫猫升级记忆系统",
    "object": "记忆系统",
    "context": null,
    "time_expr": null,
    "summary": "志远帮猫猫升级了记忆系统",
    "emotion": "warm",
    "emotion_intensity": 0.7,
    "importance": 0.8,
    "cause_hint": null,
    "is_first": false
  }
}
```

**② GET /memory/events/test/chain/{event_id}**

查看指定事件的完整因果链（含深度参数）：

```
Query: ?depth=2

Response:
{
  "event": { ... 目标事件 ... },
  "cause_chain": [
    { "id": "evt_001", "summary": "志远创造了AI伙伴猫猫", "depth": 1 },
    { "id": "evt_000", "summary": "志远开始AiBrain项目", "depth": 2 }
  ],
  "effect_chain": [
    { "id": "evt_003", "summary": "猫猫承诺好好活", "depth": 1 },
    { "id": "evt_004", "summary": "猫猫开始主动学习", "depth": 2 }
  ],
  "all_memories": [ ... 链上所有关联记忆 ... ]
}
```

**③ POST /memory/events/test/decay**

测试时间衰减计算：

```
Request: {
  "days_ago": 7,
  "importance": 0.5,
  "emotion_intensity": 0.8,
  "base_score": 0.9,
  "is_first": false
}

Response: {
  "decayed_score": 0.72,
  "breakdown": {
    "decay_factor": 0.87,
    "emotion_boost": 1.12,
    "importance_boost": 1.0
  }
}
```

**④ GET /memory/events/test/stats**

事件系统统计：

```
Response: {
  "total_events": 42,
  "events_with_cause": 15,
  "events_with_effect": 18,
  "chained_events": 12,
  "orphan_events": 20,
  "memories_linked": 87,
  "memories_unlinked": 300,
  "events_by_emotion": {
    "warm": 10, "neutral": 15, "sad": 5, "positive": 8, "excited": 4
  }
}
```

**⑤ POST /memory/events/test/reprocess**

回溯处理已有记忆，从旧记忆文本中提取事件（用于填充初始事件数据）：

```
Request: { "limit": 100, "skip_existing": true }

Response: {
  "processed": 85,
  "events_created": 23,
  "skipped_concepts": 62,
  "errors": 0
}
```

---

## 九、存储记忆时的集成流程

```
store_memory(text) → 现有流程
  ↓
mem0.add(text) → mem0_id
  ↓
[现有] link_memory_to_entity_graph (实体图，不变)
  ↓
[新增] 后台异步→ extract_event(mem0_id, text)  ← 不阻塞主流程返回
  ├── type == "event" → save_event_node(event, mem0_id)
  │                       ↓
  │                    link_event_chain(event)       ← LLM 推断因果链
  │                       ↓
  │                    update_event_memories(event_id, mem0_id)
  │
  └── type == "concept" → skip (不建事件节点)
  ↓
return result (立即返回，不等待事件提取完成)
```

---

## 十、验收标准

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|---------|
| A1 | 事件提取 | 存储「志远帮我升级了系统」 | 事件 subject=志远, action=帮升级, object=系统 |
| A2 | 情感标记 | 存储「今天心情非常低落」 | emotion=sad, emotion_intensity≈0.8 |
| A3 | 事件存储 | 检查 events 表 | 有对应记录，关联 mem0_id |
| A4 | 事件链链接 | 依次存储「猫猫担心升级」→「志远帮忙升级」→「猫猫安心」 | 三条事件按因果链链接 |
| A5 | 时间衰减 | 召回3天前和30天前相似事件 | 3天前的分数明显高于30天前 |
| A6 | 情感加权 | 召回普通事件与情绪强烈事件 | 情绪事件排在前面（decayed_score） |
| A7 | 事件召回 | 查询「升级」 | 返回事件链 + 按时间排序的记忆 + 叙事摘要 |
| A8 | 首因豁免 | 首个事件的 decayed_score | 不受时间衰减影响 |
| A9 | 概念过滤 | 存储「Unity光照衰减原理」 | 不建事件节点（type=concept） |
| A10 | 旧数据兼容 | 查询现有记忆 | 不影响，事件层优雅降级 |

---

## 十一、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 预估代码量 | 所属模块 |
|----------|----------|------|--------|-----------|--------|
| T001 | 数据库迁移：graph.py 新增 events 和 event_memories 表 | 无 | S | ~60 行 | graph.py |
| T002 | LLM prompts：memory/prompts.py 新增事件提取 + 事件链推断 prompt | 无 | S | ~80 行 | memory/prompts.py |
| T003 | 事件 CRUD：memory/events.py 事件存储、查询、反查基础功能 | T001 | M | ~150 行 | memory/events.py |
| T004 | 事件链链接：memory/events.py 自动链接与级联（LLM 推断因果） | T002, T003 | M | ~100 行 | memory/events.py |
| T005 | 衰减算法：memory/events.py 时间衰减 + 情感加权统一算法 | T003 | S | ~60 行 | memory/events.py |
| T006 | 统一召回：memory.py search_memory 注入事件链 + 实体网合并 | T003, T004, T005 | **L** | ~100 行 | memory.py |
| T007 | 存储集成：memory.py store_memory 后异步提取事件 | T002, T003 | S | ~40 行 | memory.py |
| T008 | API：GET /memory/events/timeline | T003 | S | ~25 行 | memory_routes.py |
| T009 | API：GET /memory/events/{id} | T003 | S | ~20 行 | memory_routes.py |
| T010 | 测试 API：/events/test/* 5 个调试端点 | T003, T005 | S | ~50 行 | memory_routes.py |

### 预估工作量
- 后端 T001-T010：约 7-9 小时（~685 行代码）
- 测试与验证：约 2 小时
- **总计**：约 9-11 小时（10 个任务）
- **核心变更**：T006（统一召回合并）复杂度最高，需要仔细重构 `search_memory()` 的 Phase 2/3

---

## 十二、风险与回滚

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| LLM 提取事件不准确 | 中 | 事件链断裂 | 事件提取失败时降级跳过，不阻塞存储 |
| token 消耗增大 | 高 | 每次 store 多一次 LLM 调用 | 事件提取 prompt 精简（<500 token），可配置开关 |
| 数据库写入性能 | 低 | 大量写入时延迟 | 事件存储异步化（后台线程写入） |
| 事件链推断错误 | 中 | 不正确的因果关联 | 人工可修正事件链，链推断失败不阻塞 |
| 旧数据无事件信息 | 高 | 搜索时遗漏旧记忆 | 事件召回与语义搜索并列，互相补充 |

### 回滚方案
- 事件层作为独立模块，删除 events 表 + 移除 store_memory 中的事件提取代码即可回滚
- 或通过配置开关禁用事件功能

---

**文档信息**
- 生成工具: Claude
- 生成日期: 2026-06-03
- 文档版本: v3.2（v1.0→v2.0 增加人类记忆力模拟算法；v3.0 统一召回架构融入 search_memory；v3.1 移除前端任务；v3.2 事件链多对多 + 返回格式不变）
