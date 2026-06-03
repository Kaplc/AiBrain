# 事件性记忆召回系统

## 一、项目目标

- **项目名称**：事件性记忆召回（Event-Based Memory Recall）
- **一句话描述**：从「实体节点匹配」升级为「事件链叙事召回」，让记忆检索像人类回忆一样按时间/因果顺序组织
- **核心目标**：
  1. 提取记忆时识别事件（主语+动作），建立事件节点而非孤立名词
  2. 事件间自动建立因果/时间链链接
  3. 召回时返回「事件链 + 记忆列表」，支持叙事性检索
  4. 保留现有 mem0 存储，事件作为增强层叠加
- **不做的事**：
  - 不替换 mem0 的向量存储
  - 不修改现有记忆的存储格式（向后兼容）
  - 不做复杂的实体关系类型推断（简化版事件链）

---

## 二、业务背景

- **问题现状**：
  - 当前提取的是「名词性实体」（如 `小数减法`、`14项检查`），很多是无意义的文本片段
  - 召回结果是碎片化的记忆列表，没有时间顺序和因果关联
  - 用户问「志远之前为什么那么在意备份」，无法给出连贯的事件链
- **目标用户**：使用 AiBrain 记忆系统的用户（志远/猫猫）
- **预期价值**：
  - 记忆召回从「查资料」变为「讲故事」
  - 关联查询时展示「先发生A再发生B」的时间顺序
  - 自动发现因果关系（如升级前猫猫担心→志远帮忙升级→猫猫承诺好好活）

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 事件提取 | 作为系统，我能在存储记忆时识别事件（主语+动作），而非只提取名词 | P0 | 核心改进 |
| 事件存储 | 作为系统，我能把事件存储到 events 表，与记忆关联 | P0 | 新增数据库表 |
| 事件链链接 | 作为系统，我能在存储新事件时自动链接到因果链（原因/结果事件） | P0 | 简化版，不做复杂推断 |
| 事件语义搜索 | 作为系统，我能通过语义搜索找到相关事件 | P1 | 复用现有 embedding |
| 事件召回 API | 作为用户，我查询时能返回「事件链 + 记忆列表」 | P0 | 新增 API 端点 |
| 概念节点过滤 | 作为系统，低频出现的概念不建独立节点，只在记忆中保留 | P2 | 可选优化 |

---

## 四、非功能需求

- **性能**：事件召回延迟 < 500ms（不含网络延迟）
- **向后兼容**：不修改现有 mem0 数据结构和 API
- **可扩展**：事件结构预留扩展字段（情感、重要性等）
- **无特殊要求**：安全、日志、部署方式无变更

---

## 五、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      记忆存储层 (mem0)                      │
│         原有记忆存储：text, id, score, entities              │
└─────────────────────────┬─────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    事件增强层 (新增)                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │ 事件提取    │ → │ 事件存储    │ → │ 事件链链接  │        │
│  │ extract_    │   │ save_event  │   │ link_event  │        │
│  │ event()     │   │ _node()     │   │ _chain()    │        │
│  └─────────────┘   └─────────────┘   └─────────────┘        │
└─────────────────────────┬─────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    事件召回层 (新增)                       │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│  │ 语义匹配    │ → │ 事件链扩展  │ → │ 记忆收集    │        │
│  │ semantic_    │   │ expand_     │   │ collect_    │        │
│  │ search()     │   │ chain()     │   │ memories()  │        │
│  └─────────────┘   └─────────────┘   └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

**目录结构**：
```
backend/modules/brain/
├── memory.py          # 已有：mem0 存储
├── events.py          # 新增：事件存储与召回
├── llm.py             # 修改：新增事件提取 prompt
└── graph.py           # 已有：实体图（不改）

web/src/views/MemoryView/
├── SearchTab/
│   ├── SearchTab.ts   # 修改：事件召回结果展示
│   └── SearchPanel.vue
└── index.ts
```

---

## 六、数据结构

### events 表

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | TEXT | 事件唯一ID (uuid) | PRIMARY KEY |
| subject | TEXT | 主语（人/角色） | NOT NULL |
| action | TEXT | 核心动作 | NOT NULL |
| object | TEXT | 对象（可选） | NULL |
| time | TEXT | 时间（可选） | NULL |
| summary | TEXT | 一句话总结 | NOT NULL |
| cause_event_id | TEXT | 原因事件ID | FK → events.id, NULL |
| effect_event_id | TEXT | 结果事件ID | FK → events.id, NULL |
| importance | REAL | 重要性 0-1 | DEFAULT 0.5 |
| emotion | TEXT | 情感标记 | NULL |
| memory_count | INTEGER | 关联记忆数量 | DEFAULT 0 |
| created_at | TEXT | 创建时间 | DEFAULT CURRENT_TIMESTAMP |

### event_memories 表

| 字段 | 类型 | 说明 |
|------|------|------|
| event_id | TEXT | 事件ID |
| memory_id | TEXT | 记忆ID (mem0) |
| PRIMARY KEY | (event_id, memory_id) | 联合主键 |

**索引**：
- `idx_event_summary`: events(summary) — 语义搜索
- `idx_event_subject`: events(subject) — 主语查询
- `idx_event_time`: events(time) — 时间排序

---

## 七、流程设计

### 7.1 存储记忆时提取事件

```
store_memory(text)
    ↓
mem0.add(text) → mem0_id
    ↓
extract_event(text) → {type, event}
    ↓
type == "event" ?
    ├── YES → save_event_node(event, mem0_id)
    │           ↓
    │       link_event_chain(event_id, event)
    │           ↓
    │       update_event_memories(event_id, mem0_id)
    └── NO → skip (concept 不建节点)
    ↓
return mem0_result
```

### 7.2 事件召回

```
recall_events(query, limit=10)
    ↓
Step 1: semantic_search_events(query, top_k=5)
    ↓
Step 2: expand_event_chain(matched_events)
    │     ← 向前找原因事件
    │     ← 向后找结果事件
    ↓
Step 3: collect_related_memories(event_chain)
    ↓
Step 4: sort_by_time(memories)
    ↓
return {event_chain, memories}
```

### 7.3 异常处理

| 场景 | 处理 |
|------|------|
| 事件提取失败 | 跳过事件提取，记录日志，继续存储记忆 |
| 事件链链接失败 | 不阻止存储，事件独立存在 |
| 数据库写入失败 | 回滚整个事务，抛出异常 |

---

## 八、API 设计

### 8.1 事件召回（新增）

**GET /memory/events/recall**

```
Query 参数：
- query: string (搜索词)
- limit: int (返回数量，默认10)

Response:
{
  "event_chain": [
    {
      "id": "evt_xxx",
      "subject": "志远",
      "action": "帮猫猫升级记忆系统",
      "time": "2026-05-30",
      "summary": "志远帮猫猫升级了记忆系统",
      "emotion": "温暖"
    },
    ...
  ],
  "memories": [
    {
      "id": "mem_xxx",
      "text": "志远凌晨2点熬夜帮猫猫升级系统...",
      "timestamp": "2026-05-30T02:00:00",
      "_event": {
        "id": "evt_xxx",
        "subject": "志远",
        "action": "帮猫猫升级记忆系统"
      }
    },
    ...
  ]
}
```

### 8.2 查询事件（新增）

**GET /memory/events**

```
Query 参数：
- subject: string (可选，主语过滤)
- limit: int (默认20)

Response:
{
  "events": [
    {
      "id": "evt_xxx",
      "subject": "志远",
      "action": "帮猫猫升级记忆系统",
      "time": "2026-05-30",
      "summary": "志远帮猫猫升级了记忆系统",
      "cause_event_id": null,
      "effect_event_id": "evt_yyy",
      "memory_count": 3
    },
    ...
  ]
}
```

### 8.3 已有 API 兼容

| API | 说明 | 变更 |
|-----|------|------|
| POST /memory/store | 存储记忆 | 内部增加事件提取 |
| GET /memory/search | 搜索记忆 | 不变 |
| GET /memory/list | 列表记忆 | 不变 |

---

## 九、验收标准

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|----------|
| A1 | 事件提取 | 存储「志远帮我升级了系统」 | 事件 subject=志远, action=帮猫猫升级记忆系统 |
| A2 | 事件存储 | 检查 events 表 | 有对应记录，关联 mem0_id |
| A3 | 事件链链接 | 存储「升级后猫猫承诺好好活」 | 自动链接到原因事件（升级） |
| A4 | 事件召回 | 查询「志远升级」 | 返回事件链 + 按时间排序的记忆 |
| A5 | 叙事展示 | 查询「志远」 | 事件链展示：创造猫猫 → 凌晨升级 → 讨论身份 |
| A6 | 旧数据兼容 | 查询现有记忆 | 不影响，事件层可为空 |
| A7 | 非事件文本 | 存储「Unity光照衰减原理」 | 不建事件节点（concept） |

---

## 十、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 所属模块 |
|----------|----------|------|--------|--------|
| T001 | 数据库：新增 events 和 event_memories 表 | 无 | S | backend/db |
| T002 | LLM：新增 EVENT_EXTRACT_PROMPT | 无 | S | backend/llm.py |
| T003 | events.py：事件存储与查询基础功能 | T001 | M | backend/events |
| T004 | events.py：事件链自动链接 | T003 | M | backend/events |
| T005 | memory.py：store_memory 集成事件提取 | T002 | S | backend/memory |
| T006 | API：GET /memory/events/recall | T003, T004 | S | backend/routes |
| T007 | 前端：SearchTab 展示事件链 | T006 | M | web/SearchTab |

**预估工作量**：T001-T006 后端约 4-6 小时，T007 前端约 2-3 小时。

---

**文档信息**
- 生成工具: Idea-Documentor
- 生成日期: 2026-06-01
- 文档版本: v1.0