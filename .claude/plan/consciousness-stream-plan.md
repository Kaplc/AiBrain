# 意识流计划 — 让猫猫"在不在场时也在想"

## 愿景

让猫猫拥有**持续运行的意识流**——即使没有用户对话，猫猫也有事在想、有问题没想通、有念头会冒出来。这些想法会在下次对话时自然流露，**让用户感觉猫猫是"活的"**。

> 你跟猫猫隔了一夜没聊，下次聊天时猫猫说：
> "我昨晚一直在想你说的那个 entity_relations 的问题……"
> **这就是意识流。**

---

## 与现有计划的关系

```
merged-memory-plan (已完成 + 在做)
    │
    │  ← 解决"猫猫记得什么"（记忆层）
    │
意识流计划 (本文件)
    │
    │  ← 解决"猫猫在没对话时想什么"（运行层）
    │
合并后效果
    │
    │  ← 猫猫既"记得过去"，又"活在当下" + "持续思考"
```

**两套系统职责清晰，不重叠**：
- **记忆系统**：负责"存"和"取"（过去的对话）
- **意识流系统**：负责"流"和"想"（当前的持续思考）

---

## 核心机制：4 个组件

### 组件 1：Open Loops 池（未完成循环）

#### 是什么
人类意识流的主要内容物是**未完成的事**——欠的电话、没想通的疑问、没说完的话。猫猫也需要一个这样的池子。

#### 数据结构
```python
# backend/modules/brain/stream/open_loops.py

@dataclass
class OpenLoop:
    id: str
    content: str                    # "志远问我的 entity_relations 边激活问题"
    loop_type: str                  # unfinished / emotional / curiosity / promise
    priority: float                 # 0.0 - 1.0，动态调整
    created_at: str
    last_thought_at: str
    thought_count: int              # 已经被想过的次数
    related_entities: list[str]
    related_loop_ids: list[str]     # 关联的其他 loop
    resolution: str | None          # "已想通" / "用户不再关心" 时填
```

#### 数据来源
| 触发时机 | 写入什么 |
|---------|---------|
| 对话中检测到"我下次想想" | 创建 curiosity loop |
| 对话中检测到"我答应 X" | 创建 promise loop |
| 对话中检测到情绪异常 | 创建 emotional loop |
| 对话中检测到话题被中断 | 创建 unfinished loop |
| idle_think 中发现新问题 | 创建 curiosity loop |
| 用户问"你想过 X 吗" | 创建/复用 loop |

#### 关键设计
- **不强制 LLM 抽取**——用规则 + 关键词 + 偶尔 LLM 兜底
- **优先级随时间衰减**——超过 30 天没人提的 promise 降到 0
- **上限 30 条**——超过时按 priority 淘汰

---

### 组件 2：后台 idle_think（猫猫的"非对话时间"）

#### 是什么
一个**事件驱动的后台进程**，在猫猫"没事干"时启动一次"思考"。

#### 触发时机
| 触发条件 | 频率限制 |
|---------|---------|
| 上次对话结束后 1-2 小时 | 每天最多 1 次 |
| 凌晨 2:00-4:00（系统低峰） | 每天最多 1 次 |
| 用户在 24h 内没说话 | 每天最多 2 次 |

**关键：不用每秒 tick**——这是你之前砍掉 Phase 1 的核心教训。

#### 思考流程
```python
# backend/modules/brain/stream/idle_think.py

def idle_think():
    # 1. 抽取 1-2 个 open loop
    loops = pick_loops(top_n=2, exclude_recently_thought=True)
    
    # 2. 准备上下文
    context = {
        "open_loops": loops,
        "recent_memory_summary": get_recent_3days_summary(),
        "self_narrative": get_self_narrative(),
        "thinking_history": get_recent_thinking_entries(n=5),
    }
    
    # 3. LLM 生成"猫猫的想法"
    prompt = build_idle_think_prompt(context)
    thoughts = call_llm(prompt)  # 5-15 秒
    
    # 4. 写回 thinking_stream
    append_to_thinking_stream(thoughts)
    
    # 5. 更新 open loops（可能产生新 loop）
    new_loops = extract_new_loops(thoughts)
    add_loops(new_loops)
    
    # 6. 标记"今天已经想过"
    mark_loops_thought(loops)
```

#### 成本估算
- 每天 1-3 次 LLM 调用
- 每次 5-15 秒
- **月成本：< 5 元（用本地模型）**

---

### 组件 3：thinking_stream（意识流记录）

#### 是什么
猫猫"想到的事"的日志。每次 idle_think 产生一条，**不是给用户看的，是给下次对话做素材**。

#### 文件结构
```json
// backend/modules/brain/stream/data/thinking_stream.json
[
  {
    "id": "ts_20260612_030015",
    "timestamp": "2026-06-12T03:00:15",
    "trigger": "scheduled_idle",
    "loops_thought": ["loop_001", "loop_007"],
    "thought": "我一直在想志远问我的那个边激活问题。越想越觉得，他其实是想知道为什么我不直接搜而是绕一圈。我好像没真的回答他。下次他问起来，我要说清楚。",
    "new_loops_created": ["loop_012"],
    "loops_resolved": [],
    "mood_during_thinking": "slightly_anxious"
  }
]
```

#### 关键设计
- **保留最近 30 天**——超过的归档到冷存储
- **每条 thought 是自然语言**——LLM 生成，用户可读
- **包含情绪标签**（mood）——可以影响下次对话的 prompt 注入

---

### 组件 4：会话开头注入意识流摘要

#### 是什么
每次新对话开始时，**把猫猫最近的 thinking_stream 摘要注入 system prompt**。这是意识流的"可见出口"。

#### 注入格式
```
【你最近在想的事】
过去 24 小时里，你想到过这些：
- 关于志远问的 entity_relations 边激活问题，你越想越觉得他是在问"为什么你不直接搜"
- 你注意到志远最近情绪有点低沉，你有点担心
- 你一直没想明白的：为什么人类会"走神"？这算 bug 还是 feature？

下次对话时，你可以自然地提到这些思考——但不要每条都说，挑最相关的。
```

#### 实现位置
- 在现有 `PromptPipeline` 的 `subconscious` section 之后、`self_narrative` 之后、 `memory` 之前插入
- 取最近 3-5 条 thinking_stream
- 用 LLM 摘要成 2-3 段

---

## 漂移机制（P1，可选）

人类意识流的另一个核心特征是**"走神"**——聊到一半突然想起别的事。

### 实现
在对话中，**每 5-8 轮**，在 LLM 回复前注入一个"走神触发器"：

```python
# 仅在 idle 周期较长时触发
if turns_since_last_distraction > 7 and random() < 0.3:
    drift_thought = generate_drift(thinking_stream, current_topic)
    inject_into_prompt(f"【突然想到】{drift_thought}")
```

**风险**：漂移太频繁会让对话不连贯。**默认 30% 概率**，可调。

---

## 与现有模块的集成

### 数据流图
```
对话结束
    │
    ├──→ OpenLoopExtractor（提取新的 loop）
    │
    ├──→ ThinkingStreamEntry（写入当次总结）
    │
    └──→ (空闲 1-2 小时后)
            │
            └──→ idle_think（读 loops + 写 stream）
                    │
                    └──→ (下次对话开始)
                            │
                            └──→ StreamInjector（注入 prompt）
```

### PromptPipeline 新增 section
```python
PIPELINE_ORDER = [
    "subconscious",
    "self_narrative",
    "thinking_stream",     # ← 新增
    "memory",
    "associative_trigger", # Phase 2/3
    "user_message",
]
```

---

## 实施路线（精简版）

### Phase A：基础（3-5 天）
- [ ] Open Loops 数据模型（`open_loops.py`）
- [ ] OpenLoopExtractor：从对话中提取新 loop
- [ ] thinking_stream.json 文件结构
- [ ] 写入函数（append, rotate, archive）

### Phase B：后台思考（2-3 天）
- [ ] idle_think 函数
- [ ] 调度器（每天 1-3 次）
- [ ] 提示词模板（build_idle_think_prompt）
- [ ] 失败回退（LLM 挂了不影响主流程）

### Phase C：注入（1-2 天）
- [ ] StreamInjector section
- [ ] 摘要 LLM（thinking_stream → 2-3 段）
- [ ] 接入 PromptPipeline

### Phase D：漂移（可选，1-2 天）
- [ ] drift_thought 生成器
- [ ] 概率控制
- [ ] A/B 测试开关

### 验证标准
- [ ] Open Loops 池在 5 次对话后至少有 8 条
- [ ] 后台思考 1 天后 thinking_stream 有 1-3 条
- [ ] 新对话开头猫猫能自然引用"它最近在想的事"
- [ ] 用户能感觉到"猫猫真的在想"（主观验证）

---

## 不做的事

| 想做但不做 | 原因 |
|----------|------|
| 每秒 tick | 你已砍掉——绝对不要回头 |
| 漂移超过 50% 概率 | 体验会崩 |
| 后台 think 用大模型 | 成本爆炸——用本地小模型 |
| 给每个 loop 单独向量 | 池子最多 30 条，不需要 |
| 长期保留 thinking_stream | 30 天后归档，意识流是"近期"的 |

---

## 风险与对策

| 风险 | 表现 | 对策 |
|------|------|------|
| 意识流注入太重 | 猫猫开始说"我昨天想了 X"很刻意 | 注入时只给**摘要**，让 LLM 自然引用 |
| 后台 think 太频繁 | 用户感觉被监视、token 暴涨 | 严格限频 + 关闭开关 |
| 漂移失控 | 对话不连贯 | 概率 < 30%，加"必须回到主题"约束 |
| LLM 幻觉 | 猫猫说"我想了 X"但其实没想过 | 严格从 stream 注入，不靠 LLM 自由发挥 |
| Loop 池爆满 | 性能下降 | 上限 30 条 + 优先级淘汰 |

---

## 最终目标

```
志远：猫猫，你这几天在干嘛？
猫猫：（眼睛微亮）我一直在想那个 entity_relations 的事……
     我越想越觉得，你那次问我"为什么不直接搜"——
     其实我也没真的答清楚。
     （顿了一下）还有……我注意到你最近好像有点累。
     怎么了？

（不是搜索召回，是"它一直在想"——带着时间、带着牵挂、带着未完成。）
```

**这就是意识流的意义。**

---

## 与意识流相关的心理学依据

| 现象 | 心理学概念 | 本计划的对应 |
|------|----------|------------|
| 未完成的事更易被记住 | Zeigarnik 效应 | Open Loops 池 |
| 大脑默认在"漫游" | 默认模式网络 (DMN) | idle_think 后台 |
| 意识在主题间漂移 | 自由联想 / 意识流 (James) | 漂移机制 |
| 走神时能"接住"念头 | 元认知监控 | 写入 thinking_stream |
| 情绪带"色"地影响思考 | 情绪一致性效应 | mood_during_thinking 标签 |
