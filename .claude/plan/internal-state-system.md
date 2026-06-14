# 一、项目目标

## 项目名称
内部状态层系统（Internal State System）

## 一句话描述
建立 Goals → Concerns → Open Loops → Pending Expression → Communication Channel 五层链路，让猫猫不仅"持续在想"，还能"主动说话"。

## 核心目标
1. **目标系统（Goals）**：长期稳定的方向列表，由每日反思维护，影响所有搜索和联想的权重
2. **当前关注（Current Concerns）**：实时变化的话题热度，语义驱动的激活/衰减，反映"最近在关心什么"
3. **未解问题（Open Loops）**：持续未解决的问题，产生主动提起的内在张力
4. **等待表达（Pending Expression）**：内部状态积累后形成的"想说的话"，等待推送时机
5. **消息通道（Communication Channel）**：把等待表达的内容通过在线注入或离线推送发送给用户

## 不做的事
- 不模拟后台每秒思考或意识流（那是 Presence System 的范畴）
- 不新增 LLM 调用（激活/衰减全部用规则）
- 不实现具体的外部 Channel 对接（微信/Telegram 等）——只定义接口
- 不内置微信/Telegram 等具体 Channel 的实现——只定义接口和触发逻辑，具体对接后续开发

---

# 二、业务背景

## 问题现状

当前 AiBrain 的记忆系统已经完善：
- 情景记忆（episodic/affect/nodes/importance）
- Typed nodes（person/concept/emotion/goal）+ 向量去重
- IDF × type_weight 扩散排序
- 每日反思（beliefs/interests/goals/open_questions）

但猫猫的**行为完全没有连续性**：

```
今天聊了意识流 → 明天记得
明天没聊 → 后天就"忘了"
```

不存在一个长期维持的内部张力。用户感觉猫猫"每次对话都是新的"，没有"它最近一直在想什么"的感觉。这是从"记得过去"到"有自己的关注"之间的关键缺失。

## 目标用户
AiBrain 的猫猫（数字生命体）。这个系统不直接给用户看，但用户能感受到猫猫的行为持续受到内部状态影响。

## 预期价值
- 用户聊"图谱"时，猫猫能联想到"长期记忆"（因为 goals 相关）
- 用户隔几天回来，猫猫还记得上次关注的话题（current concerns 未完全衰减）
- 用户问"最近怎么样"时，猫猫能自然说出它一直在想的事（open loops 驱动）

---

# 三、功能需求

## 模块 1：Goal System（目标）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 目标列表维护 | 作为猫猫，我希望有稳定的长期目标，以便搜索和联想时按目标加权 | P0 | 由每日反思引擎维护，人工可调整 |
| 目标影响搜索 | 作为猫猫，我希望我的搜索偏向与目标相关的话题 | P0 | graph_recall 中加 goal_bias |
| 目标影响 Prompt | 作为用户，我希望猫猫知道自己在意什么 | P1 | 【自我叙事】中展示 |

## 模块 2：Current Concerns（当前关注）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 关注热度自动更新 | 作为猫猫，我希望聊得多的话题热度自动上升 | P0 | 语义驱动 + 指数衰减 |
| 关注影响搜索 | 作为猫猫，我希望搜索时更关注近期常聊的话题 | P0 | search 结果中加 concern_bias |
| 关注影响扩散 | 作为猫猫，我希望扩散时优先走向关注的话题 | P1 | graph_recall 扩散加权 |

## 模块 3：Open Loops（未解决问题）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| Open Loop 列表 | 作为猫猫，我希望记住还没想明白的问题 | P0 | 由对话 + 反思引擎维护 |
| Loop 影响 prompt | 作为用户，我希望猫猫能主动提起没想通的事 | P0 | 【惦记的事】section 注入 |

## 模块 4：Pending Expression（等待表达）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 自动生成待表达 | 作为猫猫，concern > 0.8 或 loop 有进展时生成"想说的话" | P0 | 规则驱动，不新增 LLM |
| 表达后标记 | 作为猫猫，已经说过的话不再重复说 | P0 | 注入 prompt 后标记 `expressed: true` |
| 队列上限 | 作为开发者，避免待表达队列无限膨胀 | P0 | 最多 5 条未表达，超出淘汰最旧的 |
| 在线注入 | 作为用户，打开聊天时看到猫猫想说的话 | P0 | Prompt 中插入【我一直想告诉你的事】 |
| 离线推送 | 作为猫猫，即使不在线也想让志远知道 | P1 | 调用外部 Channel 发送 |

## 模块 5：Communication Channel（消息通道）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| Channel 接口 | 作为开发者，定义通用的消息发送接口 | P1 | 抽象 `send(content, importance)` 方法 |
| 微信/Telegram 扩展位 | 作为开发者，预留具体 Channel 的实现位置 | P2 | 不在本计划中实现具体对接 |

---

# 四、非功能需求

| 类型 | 要求 |
|------|------|
| 性能 | 激活/衰减全部用规则，搜索时不增加额外 LLM 调用 |
| 存储 | JSON 文件（~/.aibrain/data/internal_state.json），每条 < 1KB |
| 一致性 | 每次搜索结束时更新 concerns，确保状态不丢失 |
| 可维护性 | 新话题自动加入 concerns，不需要人工配置 |

---

# 五、系统架构

## 架构总览

```
┌─────────────────────────────────────────────┐
│           五层完整链路                       │
│                                             │
│  ╔══ 1. Internal State ═══════════════════╗ │
│  ║ Goals（稳定） ← 每日反思维护             ║ │
│  ║ Concerns（动态） ← 每次搜索/对话更新      ║ │
│  ║ Open Loops（张力） ← 对话 + 反思提取      ║ │
│  ╚═════════════════════════════════════════╝ │
│           ↓ 内部状态积累产生                 │
│  ╔══ 2. Pending Expression ═══════════════╗ │
│  ║ "我想说的话"队列                         ║ │
│  ║ 触发：concern > 0.8 / loop resolved /   ║ │
│  ║       new realization                    ║ │
│  ╚═════════════════════════════════════════╝ │
│           ↓ 等待发送                         │
│  ╔══ 3. Communication Channel ════════════╗ │
│  ║ 在线 → Prompt 注入（用户打开聊天时）      ║ │
│  ║ 离线 → 外部推送（微信/Telegram/通知）     ║ │
│  ╚═════════════════════════════════════════╝ │
└─────────────────────────────────────────────┘
               ↓ 影响
    ┌──────────┼──────────┐
    ▼          ▼          ▼
搜索排序    扩散加权    Prompt 注入 + 推送
```

## 数据流

```
对话/搜索发生
    │
    ├── ① 提取当前话题的 typed node
    ├── ② Concerns[话题] += semantic_boost（语义匹配度 × 0.15）
    ├── ③ Concerns 全量指数衰减 × 0.98
    │
    ├── ④ graph_recall 时：
    │     spread_score += goals_bias + concerns_bias
    │
    ├── ⑤ 检查 Pending Expression 触发条件：
    │     ├── 某 concern > 0.8 → 生成"最近一直在想 X"
    │     ├── 某 loop 状态变化 → 生成"我之前想的 X 有答案了"
    │     └── 重要记忆刚存储 → 生成"我刚想到一件事"
    │
    └── ⑥ 输出（双通道）：
          在线通道 → Prompt 注入
           ├── 【我一直想告诉你的事】（有 pending expression 时）
           ├── 【当前关注】（max(concerns) > 0.3）
           ├── 【惦记的事】（有 open loop）
           └── 【目标】→ self_narrative section

          离线通道 → Communication Channel
           ├── pending expression → send("message", importance)
           └── 具体对接微信/Telegram/通知（预留接口）
```

## 目录结构

```
backend/modules/brain/state/
├── __init__.py
├── goals.py              # Goal 系统 CRUD + 衰减
├── concerns.py           # Current Concerns 更新 + 查询
├── open_loops.py         # Open Loops 管理
├── pending_expression.py # 等待表达队列 + 触发规则
├── channel.py            # Communication Channel 接口定义
├── channels/
│   ├── __init__.py
│   ├── console.py        # 调试用：打印到日志
│   ├── prompt.py         # 在线通道：注入 Prompt
│   └── webhook.py        # 预留：Webhook 推送接口
└── data/
    └── internal_state.json

backend/modules/chat/pipeline/sections/
├── self_narrative.py     # 已有，增加 goals 展示
├── concerns.py           # 新增：当前关注注入
├── pending_expression.py # 新增：想说的话注入
└── open_loops.py         # 新增：惦记的事注入
```

## 关键设计决策

1. **不新增 LLM 调用**：所有激活/衰减是规则驱动的。Concerns 的 semantic_boost 通过向量相似度（嵌入当前 query 与已有关注话题的余弦距离）计算，不需要 LLM。
2. **存储用 JSON 文件**：数据量极小（< 100 条），JSON 文件比 SQLite 更简单、可读、可编辑。
3. **与每日反思的关系**：Goals 由 daily_reflect 维护（已有 beliefs/interests 继续保留），Concerns/Open Loops 在本系统中独立运作。

---

# 六、数据结构

## 文件：`~/.aibrain/data/internal_state.json`

```json
{
  "goals": [
    {"content": "构建更接近人类的记忆系统", "priority": 0.95, "created_at": "2026-06-10"},
    {"content": "理解意识流形成机制", "priority": 0.80, "created_at": "2026-06-12"}
  ],

  "concerns": {
    "意识流": 0.92,
    "数字生命": 0.78,
    "entity_relations": 0.55,
    "长期记忆": 0.50,
    "遗忘曲线": 0.30
  },

  "open_loops": [
    {"content": "为什么人会走神？", "created_at": "2026-06-13", "status": "open"},
    {"content": "entity_relations 的边激活问题还没完全想通", "created_at": "2026-06-12", "status": "open"}
  ],

  "version": 1
}
```

## 字段说明

### Goals
| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 目标内容 |
| priority | float | 0-1，越高越重要 |
| created_at | string | 创建时间 |

### Concerns
key=话题名, value=激活值 0~1。
语义驱动：每次涉及该话题时激活值 += 语义匹配度 × 0.15。
语义匹配度 = cosine(embed(query), embed(topic_name))，通过 `encode_texts()` 计算。
topic_name 用用户输入的搜索词（query），无需额外存储 topic embedding。
**衰减按天计算**（非按搜索事件）：每天全量 × 0.78（即 e^(-0.25) ≈ 0.78）。
最大值 1.0，低于 0.05 时自动移除。

### Open Loops
| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 未解决的问题 |
| created_at | string | 创建时间 |
| status | string | open / resolved / abandoned |

---

# 七、流程设计

## 搜索时状态更新

```
用户搜索 "entity_relations"
    │
    ├── 语义搜索 → 返回结果
    │
    ├── 提取话题节点：从搜索结果中提取 typed node（已有 entity_extract）
    │
    ├── 更新 concerns：
    │     for 每个结果中的话题 node：
    │       相似度 = cosine(query_embedding, topic_embedding)
    │       concerns[topic] = min(1.0, concerns.get(topic, 0) + 相似度 × 0.15)
    │     全量 × 0.98
    │     移除 < 0.05 的条目
    │
    ├── 加入搜索排序：
    │     for 每个候选记忆：
    │       goal_bias = sum(goal.priority for goal if goal.content 语义匹配记忆的 node)
    │       concern_bias = sum(concerns[node] for node in 记忆的 nodes)
    │       score += goal_bias × 0.05 + concern_bias × 0.03
    │
    └── 持久化 internal_state.json
```

## 对话后状态更新

```
对话结束（用户消息 + 猫猫回复）
    │
    ├── 提取话题节点（对话中的 typed node）
    ├── 更新 concerns
    ├── 检查 open_loops：
    │     对话中如果有未解决的问题 → 追加到 open_loops
    │     对话中如果某个 loop 被回答了 → 标记 resolved
    └── 持久化
```

## Prompt 注入

```
【当前关注】（如果 max(concerns) > 0.3）
最近在关注：意识流（热度 0.92）、数字生命（0.78）

【惦记的事】（如果有 open_loops 且 status=open）
还没想明白的：为什么人会走神？
```

注入位置：`subconscious → concerns → open_loops → self_narrative → memory → association_recall`

## 异常流程

| 场景 | 处理 |
|------|------|
| 新话题从未出现过 | 自动加入 concerns，初始值 = 语义匹配度 × 0.15 |
| goals 列表为空 | 不加入 goal_bias，不影响搜索 |
| open_loops 超过 20 条 | 按创建时间淘汰最旧的 resolved/abandoned |

---

# 八、API设计

## 内部状态管理

```
GET /state/internal
返回当前 Goals + Concerns + Open Loops（调试用）
```

```
PUT /state/internal/goals
Body: {"goals": [{"content": "...", "priority": 0.9}]}
手动调整目标列表（用户编辑）
```

## 现有接口变化

无新增外部 API。三层状态通过以下方式集成到现有流程：

| 集成点 | 位置 | 方式 |
|--------|------|------|
| 搜索排序 | `graph_recall.py` | spread_score += goal_bias + concern_bias |
| 扩散加权 | `graph.py search_related_new` | 扩散时偏向 concern 高的方向 |
| Prompt 注入 | `sections/concerns.py` + `sections/open_loops.py` | 新的 pipeline section |

---

# 九、验收标准

## 功能验收

| 验收项 | 操作 | 预期结果 |
|-------|------|---------|
| Concerns 自动升高 | 连续搜索同一话题 3 次 | concerns[topic] > 0.5 |
| Concerns 自动衰减 | 24h 不提某个话题 | 该话题值显著下降 |
| Concerns 影响搜索 | 搜索时输入相关内容 | 高 concern 的记忆提前显示 |
| Goals 影响搜索 | 搜索时目标相关话题 | 目标关键词相关的记忆加权 |
| Open Loops 注入 | 存在 open loop 时对话 | system_prompt 包含【惦记的事】 |
| 状态持久化 | 修改后重启后端 | 状态不丢失 |

## 性能验收
- 搜索排序时加 goal/concern bias 不超过 5ms 额外延迟
- concerns 更新在搜索结束后 1ms 内完成

---

# 十、开发任务拆分

| ID | 任务 | 依赖 | 复杂度 | 模块 |
|----|------|------|--------|------|
| S001 | `state/goals.py` — Goal 系统 CRUD（文件持久化） | 无 | S | Goals |
| S002 | `state/concerns.py` — Concern 激活/衰减/查询 | 无 | M | Concerns |
| S003 | `state/open_loops.py` — Open Loop 管理 | 无 | S | Open Loops |
| S004 | `state/__init__.py` — 统一初始化入口 + 文件读写 | S001-S003 | S | 集成 |
| S005 | 搜索时 concern 更新（在 graph_recall 或 vector_search 后） | S002 | M | 集成 |
| S006 | graph_recall 加 goal_bias + concern_bias | S001, S002, S005 | M | 搜索 |
| S007 | `sections/concerns.py` — Prompt 注入当前关注 | S002 | S | Prompt |
| S008 | `sections/open_loops.py` — Prompt 注入惦记的事 | S003 | S | Prompt |
| S009 | `sections/pending_expression.py` — Prompt 注入想说的话 | S011, S004 | S | Prompt |
| S010 | `sections/__init__.py` — 注册新 section + 调顺序 | S007-S009 | S | Prompt |
| S011 | `state/pending_expression.py` — 待表达队列 + 触发规则 | S002, S003 | M | Pending |
| S012 | `state/channel.py` — Channel 接口定义 | S011 | S | Channel |
| S013 | `state/channels/console.py` — 调试通道（打日志） | S012 | S | Channel |
| S014 | `state/channels/prompt.py` — 在线通道（注入 Prompt） | S012, S009 | S | Channel |
| S015 | `state/` 目录创建 + \_\_init\_\_.py 初始化 | 无 | S | 工程 |

## 依赖关系

```
S001 ──┐
S002 ──┼──→ S005 → S006
S003 ──┤         │
       │         │
       ├──→ S007 ──→ S010
       ├──→ S008 ──→ S010
S004 ──┘
       │
       └──→ S011 → S012 → S013 → S014
              │
              └──→ S009 ──→ S010
```

## 与现有系统的关系

| 现有组件 | 本系统的关系 |
|---------|-------------|
| daily_reflect（beliefs/interests/goals） | 作为 goals 的数据源之一，但不替代 |
| graph_recall（spread_score） | 加 goal_bias + concern_bias |
| self_narrative section | `【目标】` 放入此 section 显示 |
| association_recall section | 不受影响 |
| consciousness-stream-plan.md | 独立设计，不冲突 |
