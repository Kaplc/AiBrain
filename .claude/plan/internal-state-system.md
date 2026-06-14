# 一、项目目标

## 项目名称
内部状态层系统（Internal State System）

## 一句话描述
建立 Self → Drives → Goals → Concerns → WorkingSet → OpenLoops → PendingExpression → Refractory → Send 九层链路，让猫猫拥有持续的关注和主动表达的欲望。

## 核心目标
1. **Self Model（自我模型）**：轻量身份信息，回答"我是谁"
2. **Drives（驱动力）**：内建的基本欲望，固定值不衰减，代表人格。`Drive × Concern` 调制
3. **Goals（长期方向）**：不修改 Concern，不维持地板。只在搜索时加轻量 `goal_bias`（0.01）。Concern 和 Goal 分开：Concern 代表近期真实兴趣，Goal 代表长期方向
4. **Current Concerns（当前关注——唯一正确值）**：绑定 node_id。存 `base_activation`（全部 boost 的原始累加），不存衰减后值。运行时计算 `effective_activation = base_activation × 0.78^days_since_last_activated`。`last_activated` 既是 dormancy 来源也是衰减时间源——只存一个时间字段
5. **Working Set（近期脑海）**：短期 TTL（6h）缓存，支持 `node / memory / open_loop` 三种类型
6. **Open Loops（未解问题）**：绑定 node_id，tension = avg(effective_activation) × uncertainty。创建前检查节点重叠度 > 60% 时 merge，不新建
7. **Pending Expression（表达意图，非内容）**：只存 `source+node_id`，不存 `content`。发送时由 LLM 根据当前上下文实时生成。双路径：`recent_interest` 和 `resurfacing_interest`
8. **Refractory（冷却期）**：独立于 Pending 存储，`expression_history[node_id].refractory_until`。pending 删除不影响冷却
9. **Send Decision（事件驱动）**：状态变化后（搜索阶段）立即检查，不依赖 LLM 回复

## 不做的事
- 不新增 LLM 调用（激活/衰减/驱动力全部用规则）
- 不模拟后台每秒思考或意识流
- 不是定时器驱动
- 不做叙事层
- 不做每轮对话后的 LLM 反思
- Goal 不直接参与 Concern 维护——只用 goal_bias 影响搜索排序
- Event Layer / Interest Consolidation / Self Model 扩展 → V2

---

# 二、业务背景

## 问题现状

当前 AiBrain 记忆系统完善但行为无连续性：

- 情景记忆 / Typed nodes / IDF 扩散 / Hebbian 共现 / 联想触发 / Pending 队列 / 每日反思 ✅
- 但猫猫"每次对话都是新的"，没有"持续在关注什么"的感觉

**真正影响行为的是"当前在意什么"**，不是记忆或叙事。

## 目标用户
AiBrain 的猫猫（数字生命体）。

## 预期价值
- 行为连续：隔几天回来还记得上次关注的话题
- 主动表达：自然说出它一直在想的事
- 不复读：Refractory 冷却
- 临场感：Working Set 短期浮现

---

# 三、功能需求

## 模块 0：Self Model（轻量）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 身份信息维护 | P0 | ⚠️ 部分已有，需整合 |
| Self 注入 Prompt | P1 | ⚠️ 部分已有 |

```json
{
  "name": "猫猫",
  "traits": ["好奇", "喜欢研究记忆", "喜欢联想"],
  "relationship": {"志远": "伙伴"}
}
```
V2 扩展：likes / dislikes / speaking_style / values

## 模块 0.5：Drives（固定值）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 初始值 | P0 | ❌ |
| Drives × Concern | P0 | ❌ |

```json
{
  "curiosity": 0.8,
  "companionship": 0.9,
  "self_expression": 0.7,
  "completion": 0.6
}
```
NodeType → Drive：concept→curiosity, person→companionship, open_loop→completion, self→self_expression

## 模块 1：Goal System（仅 goal_bias，不修改 Concern）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 目标列表 | P0 | ❌ |
| Goal bias 搜索 | P0 | ❌ |

```json
{
  "name": "构建更接近人类的记忆系统",
  "priority": 0.95,
  "related_concepts": ["长期记忆", "情景记忆", "联想", "意识流", "entity_relations"],
  "created_at": "2026-06-10"
}
```
- Goal **不修改 Concern**——不维持地板、不加性 boost。Goal 代表长期方向，Concern 代表近期真实兴趣，两者分开
- 搜索时加轻量 goal_bias：`goal_bias = goal.priority × 0.01`（priority=0.95→0.0095，priority=0.3→0.003，高优先级目标才有意义）
- **搜索偏置归一化**：concern_bias、goal_bias 加入最终 score 前各自归一化到 0~1，避免不同量纲的 bias 互相压过 semantic/IDF/importance 分

## 模块 2：Current Concerns（base_activation + 运行时 effective）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 激活更新 | P0 | ❌ |
| 影响搜索 | P0 | ❌ |

```json
{
  "node_id": "node_xxx",
  "base_activation": 0.72,
  "last_activated": "2026-06-15T10:30:00"
}
```

- **存 base_activation**：全部 boost 的原始累加，不做衰减写入。`base_activation = min(1.0, base_activation + boost)`——有上限 1.0，防止一年后无限增长到 54
- **运行时计算 effective**：`effective = base_activation × (0.78 ^ days_since_last_activated)`
- **只存一个时间字段**：`last_activated`，既是休眠计算的来源也是 effective 衰减的基准
- 自动移除条件：`effective < 0.05 AND last_activated > 180天`（仅当当前冷且超过半年没提到）。只用 effective < 0.05 就移除会丢失长期兴趣历史——`base_activation=0.8` 但休眠 30 天 effective≈0，第 31 天用户再提起时 base 丢了这个信息
- 更新时机：收到用户消息后先激活 Concern，再搜索

## 模块 3：Open Loops（带 Merge）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 管理 + Merge | P0 | ❌ |
| 注入 prompt | P0 | ❌ |

```json
{
  "content": "为什么人会走神？",
  "node_ids": ["node_xxx", "node_yyy", "node_zzz"],
  "uncertainty": 0.9,
  "last_thought_at": "2026-06-15T10:30:00",
  "thought_count": 12,
  "created_at": "2026-06-13",
  "status": "open"
}
```

- 创建规则：问句句式 + 至少 1 个 concept 或 ≥2 个节点（过滤"吃了吗"）
- **Merge 机制**：创建前遍历已有 open loops，计算 Jaccard 相似度 `|A∩B| / |A∪B|`。Jaccard > 0.5 → 不创建，更新原条目的 `thought_count += 1`。用 Jaccard 而非 `|A∩B|/min(|A|,|B|)` 可避免"A=[意识流,注意力], B=[意识流,注意力,认知,海马体]"被误 merge（Jaccard=2/4=0.5 不会 merge）
- uncertainty 估算：为什么/怎么 → 0.9，是不是/能不能 → 0.7，吗/呢→ 0.5
- tension（运行时）：`avg(effective_activation_of_node_ids) × uncertainty`

## 模块 4：Working Set（多类型）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 多类型缓存 | P0 | ❌ |
| 注入 prompt | P0 | ❌ |

```json
{
  "id": "evt_xxx",
  "type": "node | memory | open_loop",
  "ref_id": "node_xxx | episodic_xxx | loop_xxx",
  "score": 0.7,
  "expire_at": "2026-06-15T16:30:00",
  "source": "search_hit"
}
```

- TTL：6h，读取时自动过滤过期
- **Upsert 语义**：同一 `ref_id` 已存在时更新 `score = max(existing, new)`，刷新 `expire_at = now+6h`，不分叉
- 来源：search_hit / association / open_loop_trigger / recent_discussion
- Prompt："最近脑海里浮现：海马体、实体关系、长期记忆"

## 模块 5：Pending Expression（存意图，不存内容）

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 自动生成 | P0 | ⚠️ 已有，需改造 |
| 去重 | P0 | ✅ |
| 队列上限 5 | P0 | ✅ |
| 写入 output | P0 | ✅ |
| Refractory | P0 | ❌ |

```json
{
  "id": "pe_xxx",
  "type": "recent_interest | resurfacing_interest",
  "source_node_id": "node_xxx",
  "expression_score": 0.72,
  "age_score": 0.15,
  "source": "concern",
  "created_at": "2026-06-15T12:00:00",
  "expressed": false
}
```

- **不存 content**：发送时由 LLM 实时生成，保证内容反映最新上下文
- **存 expression_score 快照**：生成时记录，用于后续队列排序和淘汰。每次检查 Pending 时**不重算**——否则队列顺序会漂移
- 双路径公式：
  ```
  recent_interest = effective_activation × drive_weight
  resurfacing_interest = effective_activation × dormancy_factor × drive_weight
  expression_score = max(recent_interest, resurfacing_interest)
  ```
- dormancy_factor = `min(1.0, hours_since_last_activated / 24)`

## 模块 6：Refractory（独立于 Pending）

```json
{
  "key": "recent_interest:node_xxx",
  "node_id": "node_xxx",
  "expression_type": "recent_interest",
  "last_expressed": "2026-06-15T12:05:00",
  "refractory_until": "2026-06-16T12:05:00"
}
```

- **独立存储**：`expression_history` 列表，不挂靠在 pending entry。pending 删除不影响冷却
- **key = `{expression_type}:{node_id}`**：区分同一 node 的不同表达类型。recent_interest 冷却不阻断 open_loop 表达
- 24h 默认，可动态缩减至 12h
- 判断：`now < expression_history[key].refractory_until` → novelty = 0

## 模块 7：Send Decision（事件驱动，不依赖 LLM 回复）

- 触发时机：每次 Concern / Working Set / OpenLoop 状态变化后
- 条件：有 pending 未表达 ∧ 不在睡眠时间 ∧ 上次发送超过 1h
- **优先级**：同时有多个 pending 时，按 `expression_score + age_score × 0.5` 降序取最高分发送
- 检查发生在搜索阶段完成后，不等待 LLM 回复

---

# 四、数据结构

## `internal_state.json`

```json
{
  "version": 5,

  "self_model": {
    "name": "猫猫",
    "traits": ["好奇", "喜欢研究记忆", "喜欢联想"],
    "relationship": {"志远": "伙伴"}
  },

  "drives": {
    "curiosity": 0.8,
    "companionship": 0.9,
    "self_expression": 0.7,
    "completion": 0.6
  },

  "goals": [
    {
      "name": "构建更接近人类的记忆系统",
      "priority": 0.95,
      "related_concepts": ["长期记忆", "情景记忆", "联想", "意识流", "entity_relations"],
      "created_at": "2026-06-10"
    }
  ],

  "concerns": [
    {
      "node_id": "node_xxx",
      "base_activation": 0.72,
      "last_activated": "2026-06-15T10:30:00"
    }
  ],

  "open_loops": [
    {
      "content": "为什么人会走神？",
      "node_ids": ["node_xxx", "node_yyy", "node_zzz"],
      "uncertainty": 0.9,
      "last_thought_at": "2026-06-15T10:30:00",
      "thought_count": 12,
      "created_at": "2026-06-13",
      "status": "open"
    }
  ],

  "working_set": [],

  "pending_expressions": [
    {
      "id": "pe_xxx",
      "type": "resurfacing_interest",
      "source_node_id": "node_xxx",
      "age_score": 0.15,
      "source": "concern",
      "created_at": "2026-06-15T12:00:00",
      "expressed": false
    }
  ],

  "expression_history": [
    {
      "node_id": "node_xxx",
      "last_expressed": "2026-06-15T12:05:00",
      "refractory_until": "2026-06-16T12:05:00"
    }
  ]
}
```

---

# 五、架构总览

```
               Self Model
                   │
                   ▼
              Drives（固定值）
                   │
                   ▼
          ┌── Goals（goal_bias 0.01）
          │        │
          │        ▼
          │  Working Set（6h TTL, 多类型）
          │        │
          │        ▼
          │  Concerns（base_activation 不衰减存盘）
          │  ├── effective = base × 0.78^days
          │  └── dormancy = hours_since_last_activated / 24
          │        │
          │        ▼
          │  Open Loops（Merge >60%, tension 运行时）
          │        │
          └────────┤
                   │
     用户消息 ─────┤
        │          │
        ├── update concerns + working set
        ├── search + graph（concern_bias 0.005 + goal_bias 0.01）
        ├── Pending 检查（双路径）
        ├── Send 决策（状态变化后立即）
        │          │
        ▼          ▼
       LLM ──── 回复回灌 Concern（boost 0.002）
```

---

# 六、关键设计决策

1. **Concern 存 base_activation**：不衰减写入，运行时计算 effective。`min(1.0, base + boost)` 有上限
2. **Concern 移除条件**：`effective < 0.05 AND last_activated > 180天`，防止丢失长期兴趣历史
3. **Goal 不修改 Concern**：`goal_bias = goal.priority × 0.01`，Concern 保持纯净
4. **搜索偏置归一化**：concern_bias、goal_bias 各自 0~1 后再加总
5. **Concern bias = 0.005**：轻量
6. **Pending 不存 content**：表达意图，发送时 LLM 实时生成。存 `expression_score` 快照用于队列排序
7. **Refractory key = `{type}:{node_id}`**：recent_interest 不阻断 open_loop
8. **OpenLoop Merge 用 Jaccard > 0.5**：`|A∩B|/|A∪B|`，避免稀疏合并丰富
9. **Working Set Upsert**：同 ref_id 更新 score+expire，不分叉
10. **Send 优先级**：`expression_score + age_score × 0.5` 降序
11. **自激活 boost = 0.002**
12. **Drives 固定值**

---

# 七、验收标准

| 验收项 | 预期 |
|-------|------|
| Concern 升高 | 连续聊同一话题 3 次 → base_activation > 0.5 |
| Concern 上限 1.0 | 连续激活 10 次后 base_activation = 1.0，不增长 |
| Concern 衰减 3 天 | effective = base × 0.78^3 |
| Concern 不衰减存盘 | 重启后 base_activation 不变 |
| Concern 不移除 | effective < 0.05 但 last_activated < 180天 → 保留 |
| Goal bias 区分优先级 | priority=0.95 → 0.0095，priority=0.3 → 0.003 |
| OpenLoop Merge Jaccard | [a,b] 与 [a,b,c,d] → 2/4=0.5，不 merge |
| Pending 无 content | 存 source_node_id + expression_score 快照 |
| Pending 发送优先级 | 有 3 条 pending 时发 expression_score + age_score×0.5 最高者 |
| Refractory 分类型 | recent_interest 冷却不阻断 open_loop 表达 |
| Refractory 独立 | 删除 pending 后冷却仍在 |
| Concern bias 0.005 | 5×0.8×0.005 = 0.02，不压语义分 |
| Self boost 0.002 | 50 次提及 = +0.1，安全 |
| Working Set Upsert | 同节点多次触发不分叉 |

---

# 八、开发任务

| ID | 任务 | 依赖 | 复杂度 |
|----|------|------|--------|
| S000 | self_model.py | 无 | S |
| S001 | drives.py | 无 | S |
| S002 | goals.py | 无 | S |
| S003 | concerns.py（base_activation + effective 运行时计算） | 无 | M |
| S004 | open_loops.py（带 Merge） | S003 | M |
| S005 | working_set.py（多类型） | 无 | S |
| S006 | expression_history.py（Refractory 独立存储） | 无 | S |
| S007 | __init__.py + 文件读写 + version 5 | S000-S006 | S |
| S008 | pending_expression.py 改造（不存 content + 双路径） | S003, S001, S006 | M |
| S009 | 搜索前 Concern 更新 + graph_recall bias（0.005+0.01）| S003, S007 | L |
| S010-S014 | 各 prompt section | S003-S007 | S |
