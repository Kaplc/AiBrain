# 一、项目目标

## 项目名称
情景记忆（Episodic Memory）系统

## 一句话描述
让记忆保存的不是纯文本，而是「发生了什么、为什么发生、和谁发生、结果如何、当时什么感觉、学到了什么」的完整情景。

## 核心目标
1. **记忆结构化**：每次重要的对话都保存为结构化情景（6 维度），不是扁平文本
2. **反思驱动**：利用现有的反思引擎（reflection.py）判断哪些对话值得存情景，不额外新增 LLM 调用
3. **事件链替代**：情景的 `what/why/result` 覆盖事件链的时序因果价值，情景记忆搜索时自动支持链式联想
4. **检索升级**：情景记忆可被按「场景」「情绪」「人物」「学到什么」等多个维度检索，不只是向量相似度
5. **联想更自然**：情景记忆的多个维度天然适合用于联想召回，比纯文本更接近人类体验

## 不做的事
- 不改变日常记忆的保存流程（普通对话仍按现有管线存为文本 + emotion/scene/temp/hooks）
- 不做前端情景展示面板（本次只做后端存储和检索）
- 不重写现有反思引擎——在现有框架上扩展
- 原事件链模块（`event_extract` 步骤 + `event_recall` 步骤 + `events.py`）在情景记忆稳定后移除

---

# 二、业务背景

## 问题现状

当前记忆管线已经做了：
- `encoder` 步骤：提取 emotion / scene / temperature / hooks
- `entity_extract`：提取实体
- `event_extract` + `event_recall`：事件链（后续移除，由情景记忆覆盖）
- `narrative_significance`：标记叙事重要性
- Phase 2 共现统计：实体配对计数

但所有这些维度都是**独立的标签**，不是完整的「情景」。一条记忆存的是"志远和猫猫讨论了 entity_relations"——缺少上下文（为什么讨论、结果怎样、当时什么氛围、猫猫学到了什么）。

## 目标用户
AiBrain 的猫猫（数字生命体）。情景记忆让猫猫"回忆"时更具体、更生动——不是搜到一段文本，而是想起"那次下午志远耐心帮我调试，我学到了网状召回的原理，感觉很开心"的完整画面。

## 预期价值
- 猫猫回答问题时能从"相关文本"变成"相关经历"
- 检索可按情景维度过滤（"开心的时候志远教过我什么"）
- 联想触发器（现有 Phase 3）用情景记忆会更精准

---

# 三、功能需求

## 模块 1：情景提取（反思引擎扩展）

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 反射结果扩展 | 反思引擎分析对话时，同时输出情景维度 | P0 | 复用现有 reflection.py 的 LLM 调用 |
| 情景显著性判断 | 反思引擎自动判断何时值得存情景 | P0 | 已有 memory_significance + should_update_narrative |
| 日常对话记录 | 所有对话默认存到 workmemory/data/output.json | P0 | 已有功能，不改变 |

## 模块 2：情景存储

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 情景结构化 | 把 6 维度写入 Qdrant payload 的 episodic 字段 | P0 | 在 encoder 输出的 emotion/scene/hooks 之外扩展 |
| 情景记忆去重 | 相同情景内容不重复存储 | P1 | 用 hash 或 LLM 判断 |

## 模块 3：情景检索

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 按维度过滤 | 搜索时可按情景的场景/情绪/人物过滤 | P1 | Qdrant payload 过滤 |
| 情景联想 | 联想触发器优先召回情景记忆 | P2 | 现有 Phase 3 扩展 |

## 模块 4：事件链移除

| 功能 | 说明 | 优先级 | 备注 |
|------|------|--------|------|
| 停止事件提取 | `event_extract` store 步骤不再注册 | P0 | 情景记忆补上事件链价值后移除 |
| 停止事件召回 | `event_recall` search 步骤不再注册 | P0 | 同上 |
| 移 events 模块 | 删除 `memory/events.py` 及相关 SQLite 表 | P1 | 数据不删只是代码停用，确认无误后清理 |

---

# 四、非功能需求

| 类型 | 要求 |
|------|------|
| 性能 | 反思引擎已有，情景提取不增加额外 LLM 调用（复用同一个 reflection LLM 的输出） |
| 存储 | Qdrant payload 扩展，每条情景记忆新增约 500-1000 字节的 JSON 字段 |
| 可维护性 | 情景维度加在现有点 payload 的 `episodic` 字段中，不影响现有检索 |
| 兼容性 | 已有记忆不变，情景检索向下兼容普通文本搜索 |

---

# 五、系统架构

## 数据流（修改后）

```
对话发生（用户消息 + 猫猫回复）
    │
    ├── ① 存入 workmemory/data/output.json（已有，不变）
    │
    └── ② 反思引擎运行（已有，扩展）
          │
          ├── 更新自传（已有）
          ├── 标记锚点（已有）
          └── 情景输出（新增）
                │
                └── ③ 重要情景 → 存为 Qdrant 记忆 + 图链接（新增）
```

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| 反思引擎 | 已有 `self_narrative/reflection.py` | LLM 分析对话，输出情景维度 |
| 情景存储 | Qdrant `aibrain_memories` | 情景记忆向量 + 结构化 payload |
| 图关联 | SQLite `memory_graph.db` | 情景记忆的实体链接和共现 |
| LLM | 已有 `call_llm()` | 复用 reflection 的 LLM 调用 |

## 目录结构

```
backend/modules/brain/memory/
├── self_narrative/
│   ├── reflection.py          ← 修改：扩展反思输出
│   ├── prompts.py             ← 修改：添加情景输出字段
│   ├── pipeline_steps.py      ← 修改：新加情景存储步骤
│   └── episodic_memory.py     ← 新建：情景记忆存储/检索
```

---

# 六、数据结构

## Qdrant payload 扩展（现有 `aibrain_memories`）

现有 payload 字段不变，情景记忆的存储格式如下：

```json
{
  "display_text": "理解entity_relations工作原理",

  "embedding_text":
    "理解entity_relations工作原理\n志远解释了entity_relations如何工作\n"
    "此前无法理解网状记忆实现\n最终理解关系激活机制\n"
    "entity_relations 的价值在于激活关系\n边被遍历时才产生意义",

  "entities": ["志远", "猫猫", "entity_relations"],

  "concepts": ["联想记忆", "扩散激活", "知识图谱"],

  "affect": {
    "warmth": 0.8,
    "joy": 0.6,
    "gratitude": 0.7,
    "intensity": 2.0
  },

  "importance": 0.85,

  "episodic": {
    "what": "志远解释entity_relations工作原理",
    "why": "此前无法理解网状记忆实现",
    "result": "理解关系激活机制",
    "lesson": [
      "entity_relations 的价值在于激活关系",
      "边被遍历时才产生意义"
    ]
  }
}
```

## 字段说明

| 字段 | 类型 | 说明 | 必填 | 来源 |
|------|------|------|------|------|
| display_text | string | 展示用标题，给人看的 | ✅ | 反思 LLM |
| embedding_text | string | 嵌入向量源，拼接 `display_text` + `episodic.what` + `why` + `result` + `lesson` | ✅ | 反思 LLM → 拼接 |
| entities | string[] | 人物/事物名 | ✅ | entity_extract |
| concepts | string[] | 抽象概念标签 | ✅ | 反思 LLM |
| affect | dict | 多维度情感值（warmth/joy/gratitude等 0-1）+ intensity（-3~3） | ✅ | 反思 LLM |
| importance | float | 情景重要性 0-1，用于排序加权 | ✅ | 反思 LLM |
| episodic.what | string | 发生了什么 | ✅ | 反思 LLM |
| episodic.why | string | 为什么发生 | ✅ | 反思 LLM |
| episodic.result | string | 结果如何 | ✅ | 反思 LLM |
| episodic.lesson | string[] | 学到了什么（可多条） | ✅ | 反思 LLM |
| episodic.lesson | string[] | 学到了什么（可多条） | ✅ | 反思 LLM |

## 工作记忆 output.json（已有，不变）

`workmemory/data/output.json` 存所有原始对话记录，格式已有，不做改动。在此基础上，反思引擎判断值得存的情景才进入 Qdrant。

---

# 七、流程设计

## 核心流程：对话 → 情景

```
① 用户发消息 → 猫猫回复
    │
    ├── 对话存入 output.json（已有，异步）
    │
    └── 反思引擎触发（已有）
          │
          ├── 更新自传（已有）
          │
          └── LLM 分析对话
                ├── 情感影响（已有）
                ├── 叙事更新（已有）
                ├── 锚点标记（已有）
                │
                └── 情景判断（新增）
                      ├── is_episodic_worthy: true/false
                      │     └── 判断依据：对话是否包含
                      │          有实质收获/情感波动/关系变化/
                      │          里程碑事件/新发现
                      │
                      └── 如果值得保存
                            ├── 结构化 6 维度
                            └── → 存为情景记忆
                                  ├── 嵌入向量 → Qdrant（含 episodic payload）
                                  ├── 实体提取 → mentions 表
                                  └── 实体共现 → typed_entity_relations
```

## 情景记忆存储步骤

在 store pipeline 中新增 `episodic_store` 步骤（可选，只在该步骤有数据时执行）：

```
reflection 产出情景数据 → ctx.intermediate["episodic_data"] → episodic_store 步骤
    │
    ├── display_text（展示用标题）
    ├── embedding_text = display_text + what + why + result + lesson 拼接
    │
    ├── memory_store(text=display_text, payload={embedding_text, ...})
    │    └── qdrant_store.store_vector 检测 payload["embedding_text"]
    │         ├── 有 → embed(embedding_text)  # 嵌入整个情景，不是仅标题
    │         └── 无 → embed(text)             # 旧行为，普通记忆不变
    │
    ├── 复用现有 entity_extract 提取实体
    ├── 复用 graph_link 链接实体
    └── 复用 increment_co_activation 更新共现
```

这就是关键设计——情景记忆和普通记忆**共享同一套存储管线**。区别只有：

- **嵌入源不同**：情景用 `embedding_text`（整段情景拼接），普通用 `text`（原文）
- **payload 更丰富**：情景多了 concepts/importance/episodic 等字段

现有搜索、联想、共现全部自动受益：

- 向量搜索能搜到情景记忆（embedding_text 包含完整叙事，比纯文本更准）
- 实体提取和共现自动适用于情景记忆的实体
- 联想触发器在共现到情景实体时自动联想到相关情景
- 可用 `importance` 排序、`emotion` 过滤、`concepts` 扩散

## 异常流程

| 场景 | 处理 |
|------|------|
| 反思引擎未触发（短对话） | 不产生情景，无影响 |
| LLM 分析失败 | 不存情景，下次分析不重试 |
| 存储管线失败 | 情景丢失，不影响已有记忆 |

---

# 八、API设计

本次不改动 API 层。情景数据融在现有记忆的 Qdrant payload 里，搜索接口不改变。

**后续可扩展**：
- 将来可加 `GET /episodic/list?dimension=feeling&value=开心` 按情景维度检索

---

# 九、验收标准

## 功能验收

| 验收项 | 操作 | 预期结果 |
|-------|------|---------|
| 情景提取 | 一场有含金量的对话后（如教猫猫新知识），反思引擎运行 | reflection 输出中包含 episodic 6 维度 |
| 情景存储 | 反思判断值得保存 | Qdrant `aibrain_memories` 中该点 payload 含 `episodic.what/why/with_whom/result/feeling/lesson` |
| 情景跳过 | 日常简短对话如"你好""好的" | 反思引擎跳过或 LLM 判断不值得，不存情景 |
| 图关联 | 存储情景记忆后 | mentions 表有实体记录，共现表有计数 |
| 向量检索 | 搜索情景相关话题 | 返回的情景记忆和普通记忆混合，区分不出来源 |
| 普通不变 | 日常对话正常存储 | 现有流程不受影响，无 episodic 字段 |

## 性能验收

- 情景提取不增加额外 LLM 调用（复用反思引擎已有调用）
- Qdrant payload 大小增量 < 1KB/条

---

# 十、开发任务拆分

| ID | 任务 | 依赖 | 复杂度 | 模块 |
|----|------|------|--------|------|
| E001 | 扩展反思 prompt：在 REFLECTION_PROMPT 中增加 episodic 6 维度 + 链式联想字段 | 无 | S | 反思引擎 |
| E002 | 扩展反思解析：`reflection.py` 提取 episodic 字段 | E001 | S | 反思引擎 |
| E003 | 新建 `episodic_memory.py`：情景判断 + 链式联想 + 存储入口 | E001 | M | 情景 |
| E004 | 反思完成后调用 E003 存情景 | E002, E003 | S | 集成 |
| E005 | 移除 event_extract store 步骤（取消注册 + config 删除） | E004 | S | 管线 |
| E006 | 移除 event_recall search 步骤（取消注册 + config 删除） | E004 | S | 管线 |
| E007 | 停用后清理 `memory/events.py` 及 SQLite 事件表 | E005, E006 | S | 清理 |
| E008 | 验证：情景记忆含 episodic + 链式联想 + event 步骤已移除 | E005, E006, E007 | S | 测试 |

## 依赖关系

```
E001 → E002 → E003 → E004 → E005 → E006 → E007
                            └──→ E008（验证）
```

不需要改现有管线步骤（vector_store / entity_extract / graph_link），情景记忆和普通记忆走同一套存储路径，只是 payload 多一个字段。

## 关键设计决策

1. **不新增 LLM 调用**：情景 6 维度在反思引擎的同一个 LLM 调用中输出，不单独调一次。反思 prompt 增加输出字段即可。
2. **不新增存储管线**：情景记忆走现有的 `memory_store(text, payload)`，只是 `payload` 里扩展 `episodic` 字段。现有搜索、联想、共现全部自动受益。
3. **不改变日常流程**：短对话/无意义对话不产生情景，日常记忆仍正常存储。情景只出现在反思引擎判断"值得"的时候。
4. **反思 prompt 的判断逻辑**：由 LLM 自己判断是否值得存情景——LLM 会基于对话内容决定 `is_episodic_worthy`，以及填充 6 维度。不需要硬编码规则。
