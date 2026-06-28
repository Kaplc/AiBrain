# AiBrain 架构分析与改进方向

> 基于 2026-06-28 会话整理。
> 涵盖 Day/Alive/Sleep Tick 昼夜节律、AutonomousMind 意识流循环、Prompt 体系全景与认知科学指导原则。

---

## 一、背景

从 `output.json` 观察到 AI（猫猫）的自主消息存在严重的机械重复问题：
seq 292-346 共 **50+ 条**消息几乎都在表达"语义网络类型标记改造"这一件事。

深入代码后发现，这不是一个表面 bug，而是**整个决策链路设计哲学**的问题——系统层层替 AI 做决定，AI 从未被允许自主决定"想做什么"。

---

## 二、昼夜节律与意识流循环

### 2.1 整体架构

**三层结构：**

```
LifeScheduler（调度器）→ 控制昼夜节律 + 触发 AutonomousMind
  │
  ├─ _day_tick()     醒来仪式：读身份文件 + Python 管理器 + 环境 → Working Memory
  ├─ _loop() → _fire() → daemon.run_consciousness_tick()
  │     └→ AutonomousMind.tick()   意识流决策（think/use_tool/speak/rest）
  └─ _sleep_tick()   睡前仪式：consolidation + 清空 Working Memory
```

调度器 `scheduler.py` 和意识流决策器 `autonomous_mind.py` **是两个独立模块**——调度器负责"什么时候醒/睡"，决策器负责"醒了做什么"。

### 2.2 人的一天 vs AI 的一天

| 时间 | 人 | AI（当前） | AI（改进后） |
|:-----|:---|:-----------|:-------------|
| 早起 | 恢复意识、看时间、回忆昨天 | — | **Day Tick：** 读身份文件 + 环境 → Working Memory |
| 白天 | **活着**（事件循环，没大事就发呆） | 每 30min 一次意识流 | 每 30min 一次 **AutonomousMind.tick()** |
| 睡前 | 回想一天、写日记、清空大脑 | — | **Sleep Tick：** consolidation + 清空 WM |
| 睡眠 | 记忆巩固（慢波+REM） | 无（永远醒着） | 长时间无 tick → 自然 idle |

> **关键差异：** 每次 AutonomousMind.tick() 都是**给 AI 一个机会自主决定**。AI 可以选 `rest`（安静待着），可以选 `think`（内心活动），可以选 `use_tool`（探索），也可以选 `speak`（说话）。

### 2.3 完整调度流程

```
scheduler.start()
  → _day_tick()
      → 读 prompts/identity/{self,goals,open_loops}.md
      → 读 Python 管理器（Self / Goals / OpenLoops）
      → _scan_environment()
      → 写入 Working Memory
      → _enqueue_consolidation("daily")
  → 进入 alive 循环
      → _fire() → daemon.run_consciousness_tick()
          → AutonomousMind.tick()
              → _perceive() 检测变化
              → _need_reasoning()  ← 关键门
                  → Yes → 内循环 use_tool → ... → think/speak/rest
                  → No  → skip LLM（省 token）
      → _maybe_sleep_tick()（深夜检测）
      → _maybe_day_tick()（清晨检测）
      → _sleep(1800)
  → scheduler.stop()
  → _sleep_tick(reason="scheduler_stop")
```

### 2.4 Day Tick 设计

Day Tick 的产出是**初始 Working Memory**。身份信息从 `prompts/identity/` 的 .md 文件 + Python 管理器共同读取：

```
醒来
  ↓
读取 prompts/identity/self.md + SelfModelManager   → "我是猫猫，性格好奇随性"
  ↓
读取 prompts/identity/goals.md + GoalManager       → "目标：理解代码库、学习新知识"
  ↓
读取 prompts/identity/open_loops.md + OpenLoopManager → "未解问题"
  ↓
扫描环境                          → 当前时间 + 用户状态
  ↓
形成初始 Working Memory（4±2 条） → 开始 Alive 循环
```

> **"扫描环境"是什么？** 对于一个没有眼睛耳朵的数字生命体，"环境"就是系统内部状态：当前时间、日期、周几、用户多久没说话了、最后一次聊天内容、是不是深夜。**不是去外部拉数据**，而是把已有状态信息做一次整理打包。AI 没有传感器，它的全部"环境"都在内存和持久化状态里。

```python
def _scan_environment(self) -> list[str]:
    """Day Tick 时整理环境信息（不是外部感知，是状态打包）。
    
    对于数字生命体，"环境" = 系统内部状态。没有传感器，
    只是把已有的时间/用户状态整理成文本。
    """
    env = []
    
    # 1. 时间信息（当前有 _time_of_day() ✅，缺日期/周几）
    now = datetime.now()
    weekday_map = {0:"周一",1:"周二",2:"周三",3:"周四",4:"周五",5:"周六",6:"周日"}
    time_of_day = self._time_of_day()  # ✓ 已存在
    env.append(f"现在是{weekday_map[now.weekday()]}，{time_of_day}")
    
    # 2. 用户活跃度（已有 idle_seconds ✅）
    idle = life_state.get("idle_seconds", 0)
    if idle < 60:
        env.append("志远刚还在")
    elif idle < 1800:
        env.append(f"志远已经离开{idle//60}分钟了")
    else:
        env.append(f"志远已经离开{idle//3600}小时了")
    
    # 3. 最后聊天内容（已有 ✅）
    last_chat = self._recent_chat(limit=1)
    if last_chat:
        env.append(f"最后聊到：{last_chat[:60]}")
    
    # 4. 当前系统活跃度（新增：检测是否有未读事件等）
    is_busy = _is_chat_busy()  # ✓ 已存在
    if is_busy:
        env.append("志远正在和我聊天")
    
    return env
```

```python
def _day_tick(self):
    """Day Tick：读身份文件 + Python 管理器 + 环境 → 构建初始 WM。"""
    wm = []
    
    # 1. 身份文件（AI 可编辑，>5 字符有效）
    for fname in ("self.md", "goals.md", "open_loops.md"):
        wm.append(_read_identity_file(fname))
    
    # 2. Python 管理器补充（Self / Goals / OpenLoops）
    sm = get_self_model().get()
    wm.append(f"我是{sm.get('name','猫猫')}，性格{'、'.join(sm.get('traits',[]))}")
    goals = get_goals().get_all()
    for g in goals[:3]:
        wm.append(f"目标：{g.get('name','')}")
    loops = get_open_loops().get_open()
    for l in loops[:3]:
        wm.append(f"没想完：{l.get('content','')}")
    
    # 3. 环境信息
    wm.extend(self._scan_environment())
    
    # 4. 写入 Working Memory + 清空 internal_dialogue
    state.replace_working_memory(wm[-6:])
    state.mutate_stream(lambda s: s.update({"internal_dialogue": []}))
    
    # 5. 触发每日 consolidation
    self._enqueue_consolidation("daily")
```

> **注意：** 实际代码同时读身份文件 AND Python 管理器——身份文件让 AI 可编辑，管理器保证基础数据不丢。身份文件优先（追加到 WM），管理器在后兜底。

### 2.4-a Prompt 身份文件——AI 可编辑的自我认知

身份信息全部来自 `prompts/identity/` 下的 3 个 .md 文件，**AI 可用 `write_file` 自主修改**：

> **生效时机：** 身份文件在 Day Tick 时读入 Working Memory。Alive Tick 的 `_build_context()` 从 Working Memory 读取，不重新读文件。AI `write_file` 后，需要**等下一个 Day Tick**（清晨）或**手动触发 Day Tick** 才能生效。

**Alive Tick 读取身份文件：**

```
_alive_tick()
  use_tool → read_file("prompts/identity/goals.md")
  → "我想加一个新目标：学习 Rust 异步编程"
  → use_tool → write_file("prompts/identity/goals.md",
      "1. 学习 Rust 异步编程")
  → 下个 Day Tick 清晨重读身份文件 → 写入 WM → 生效
```

| 维度 | 说明 |
|:-----|:------|
| **数据源** | `.md` 文件（唯一来源） |
| **AI 可修改** | ✅ `use_tool → write_file`（覆盖模式） |
| **人类可编辑** | ✅ 直接用文本编辑器 |
| **生效时机** | 下次 Day Tick 时重读（最长 ~24h） |
| **容错** | 文件损坏 → 从 Python 管理器兜底读取；AI 也可 `write_file` 修复 |

> **实际实现：** 身份文件和 Python 管理器**并存**。身份文件给 AI 自主编辑能力，管理器保证基础认知不丢。

**风险与缓解：**

| 风险 | 缓解 |
|:-----|:------|
| 文件被写为空/脏数据 | 读文件时加 `content.strip() >= 5` 校验，脏数据跳过 |
| 文件无限膨胀 | `write_file` 为覆盖模式（非追加）；读时只取 `[:200]` |
| AI 静默修改身份 | 每次 Day Tick 时重新读取，无需额外检测（天然反映文件状态） |
| 身份演化"过界" | 无自动回退，但人类可直接编辑 .md 文件恢复 |

### 2.5 AutonomousMind.tick() —— 意识流决策循环

**一次 `AutonomousMind.tick()` = 感知 → NeedReasoning? → 内循环 → 返回。** 由 scheduler 每 30min 触发一次：

```python
# scheduler._loop() → _fire() → daemon.run_consciousness_tick()
#   → autonomous_mind.tick()

def tick(self, ctx):
    # 1. 感知环境变化（diff 检测）
    signals = self._perceive(life_state)
    
    # 2. NeedReasoning? 门（无事发生就 skip，省 token）
    if not self._need_reasoning(signals):
        self._rest_streak += 1
        return {"action": "rest", "llm_skipped": True}
    
    # 3. 内循环：use_tool 可连续多轮
    for cycle in range(max_cycles):
        context = self._build_context(ctx, loop_ctx)
        decision = self._llm_decide(context)
        action = decision["action"]
        
        if action == "use_tool":
            result = self._execute_tool(decision)
            loop_ctx["last_result"] = result      # 注入下一轮
            loop_ctx["accumulated"].append(result)
            continue
        
        # think / speak / rest / create_activity → 终止
        self._execute_action(decision)
        return {"action": action, ...}
    
    return {"action": "rest", "reason": "max_cycles"}
```

> **注意：** 实际代码中 `autonomous_mind.py` 保留了内循环（`max_cycles=6`），不是一步。这是有价值的——`use_tool` 连续查找比跨 6 个 tick（3h）快得多。但 speak/think/rest 仍然是终止动作。scheduler 不控制动作类型，只控制"什么时候 tick"。

### 2.6 `_perceive()` —— 数字生命的感知（在 AutonomousMind 内）

对数字生命来说，"感知"不是摄像头/麦克风，而是**检测系统状态的变化**：

```python
def _perceive(self, life_state: dict) -> dict:
    """检测系统状态变化（diff 检测）。
    
    对比当前状态与上次 tick 的快照，找出变化。
    没变化 → 返回空信号 → NeedReasoning? = No → 跳过 LLM。
    """
    signals = {}
    last = self._last_perceived_state
    
    # 1. 用户活跃度变化
    now_idle = int(life_state.get("idle_seconds", 0) or 0)
    if abs(now_idle - last.get("idle", 0)) > 60:
        signals["idle_changed"] = True
        if last.get("idle", 0) > 0 and now_idle < last["idle"] - 60:
            signals["idle_dropped"] = True  # 用户刚回来
    
    # 2. 用户是否刚说了话（output 条目数变化）
    current_count = len(get_work_memory().output_mem_read())
    if current_count > last.get("output_count", 0):
        signals["user_message"] = True
    
    # 3. 时间跨入新的时段 / 跨天
    now_period = self._time_of_day()
    now_date = times.now().strftime("%Y-%m-%d")
    if now_period != last.get("period"):
        signals["period_changed"] = now_period
    if now_date != last.get("date"):
        signals["day_changed"] = True
    
    # 缓存本次结果供下次 diff
    self._last_perceived_state = {
        "idle": now_idle, "output_count": current_count,
        "period": now_period, "date": now_date,
    }
    return signals
```
        signals["period_changed"] = now_period
    
    # 4. 跨天了（日期变化 → 触发 Day Tick）
    now_date = datetime.now().strftime("%Y-%m-%d")
    if now_date != last_state.get("date"):
        signals["day_changed"] = True
    
    # 缓存本次结果供下次 diff
    self._last_perceived_state = {
        "idle": now_idle,
        "last_seq": current_seq,
        "period": now_period,
        "date": now_date,
    }
    
    return signals
```

> **注意：** 所有"感知"的输入源都来自**已有的系统状态**（life_state、output.json、clock）。
> 不新增任何外部接口。`_perceive()` 本质就是做**状态对比**——和上一轮 tick 的快照做 diff。

### 2.7 Sleep Tick 设计

由 scheduler 在深夜（23:00-02:00）和 `stop()` 时触发。**每"夜"最多一次**（跨天归一到起始日）：

```python
def _sleep_tick(self, *, reason="deep_night"):
    # 1. 触发记忆 consolidation（后台线程，不阻塞）
    if cfg.get("sleep_tick_consolidate", True):
        self._enqueue_consolidation("idle")
    
    # 2. 清空 Working Memory
    state.clear_working_memory()
    
    # 3. 记录睡眠会话（防跨天重复触发）
    #    23:00 后用当天日期，0:00-2:00 用昨天日期
    self._last_sleep_session = session_id
```

**触发时机：**
- 每天 23:00-02:00 区间的 alive tick 执行完后追加
- `scheduler.stop()` 时强制触发一次（系统关闭 = AI 睡觉）

### 2.8 三级结构总结

| Tick 类型 | 频率 | LLM | 核心产出 |
|:----------|:-----|:-----|:---------|
| **Day Tick** | 每天清晨 + 启动 | ❌ | **初始 Working Memory**（身份文件 + 管理器 + 环境） |
| **AutonomousMind.tick()** | 每 ~30min | 按需 | **感知 → NeedReasoning? → 内循环 use_tool → 终止** |
| **Sleep Tick** | 每天深夜 + 停止 | ❌ | consolidation + 清空 WM |

### 2.9 NeedReasoning? 门的触发条件

```python
def _need_reasoning(self, signals) -> bool:
    # 1. 用户刚说过话 → 需要
    if signals.get("user_message"):
        return True
    # 2. 用户刚回来（idle 大幅下降）→ 需要
    if signals.get("idle_dropped"):
        return True
    # 3. 连续 rest 够了 → 需要（跳出 rest 循环）
    if self._rest_streak >= 3:
        self._rest_streak = 0
        return True
    # 4. 跨天了 → 需要
    if signals.get("day_changed"):
        return True
    # 5. 默认：不调 LLM
    return False
```

### 2.10 配置

在 `config.py` 中新增：

```python
"day_tick_hour_start": 6,        # Day Tick 触发起始小时（24h）
"day_tick_hour_end": 8,          # Day Tick 触发结束小时
"sleep_tick_hour_start": 23,     # Sleep Tick 触发起始小时
"sleep_tick_hour_end": 2,        # Sleep Tick 触发结束小时（跨天）
"sleep_tick_consolidate": True,  # Sleep Tick 时是否触发记忆 consolidation
"working_memory_capacity": 6,    # Working Memory 容量（4±2）
"alive_attention_enabled": True, # 是否启用感知→Attention 门
```

---

## 三、Prompt 体系全景

### 3.1 三个 LLM 调用路径

#### 路径 1：后台意识流 tick（`autonomous_mind.md`）

```
System: prompts/autonomous_mind.md（人格设定 + 5 种 action 定义 + 决策原则）
User:   实时装配的上下文（last_thought / concerns / already_said / activities / 工具结果）
```

#### 路径 2：聊天思考（`brain_judge_reactive.md` → BrainJudge）

```
System: prompts/brain_judge_reactive.md
User:   judge_view JSON（user_message / memory_context / tool_results / procedure_matches）
```

#### 路径 3：聊天回复（7 个 section 拼装 → ChatLoop）

由 `pipeline/sections/` 下的 7 个模块按序拼装：

| 顺序 | Section | 文件 | 内容 |
|:----:|:--------|:-----|:-----|
| 1 | subconscious | `subconscious.py` | 人格设定 + 优先使用对话上下文规则（稳定块） |
| 2 | self_narrative | `self_narrative.py` | 当前心情、在想什么、信念/兴趣/目标 |
| 3 | memory | `memory.py` | 语义搜索结果（参考信息） |
| 4 | association_recall | `association_recall.py` | 话题实体的历史关联记忆（图共现） |
| 5 | internal_state | `internal_state.py` | 在意的 top-5 事、未决问题、想提的事 |
| 6 | brain_context | `brain_context.py` | BrainJudge 的思考摘要 + 回复策略 |
| 7 | skills_inject | `skills_inject.py` | 当前加载的技能 + 可用列表 |

**再加上：** 历史对话（`chat_history.py`）+ 工具记忆 + 用户当前消息

### 3.2 Prompt 文件清单

| 文件 | 路径 | 阶段 | 调用者 | 说明 |
|:-----|:-----|:-----|:-------|:------|
| `autonomous_mind.md` | `prompts/` | 后台意识流 | `AutonomousMind._call_llm()` | 意识流决策 prompt。⚠️ 工具列表缺 `write_file` |
| `brain_judge_reactive.md` | `prompts/` | 聊天思考 | `BrainJudge._call_llm()` | reactive session 内循环决策 |
| `brain_judge_idle.md` | `prompts/` | 旧后台（已弃用） | 旧 `BrainJudge` | 被 `autonomous_mind.md` 取代 |
| `brain_arbiter.md` | `prompts/` | 仲裁（已弃用） | 旧 `Arbiter` | 被意识流取代 |
| `final_reply.md` | `prompts/` | **架构文档** | 控制 | 定义 `reply_strategy` 的 JSON schema（`controller.py` L259 参考该格式） |
| `self.md` | `prompts/identity/` | Day Tick（规划中） | `_day_tick()` | AI 可编辑的身份描述 |
| `goals.md` | `prompts/identity/` | Day Tick（规划中） | `_day_tick()` | AI 可编辑的长期目标 |
| `open_loops.md` | `prompts/identity/` | Day Tick（规划中） | `_day_tick()` | AI 可编辑的未解问题 |

### 3.3 活动文件注入链路（旧系统，仅供参考）

```
activities/*.md
  → registry.reload_all() → ActivityDef
  → daemon.run_tick() → selected_activity（仅字符串）
  → BrainRunContext → to_judge_view()
  → judge._system_prompt() 替换 {activity}
```

**注意：** 该链路随 `brain_judge_idle.md` 的弃用而不再活跃。意识流不依赖活动文件，AI 通过 `create_activity` 自主创建跨 tick 活动。

---

## 四、认知科学指导原则（用户分析）

> 以下为用户在对话中提出的架构洞察，被采用为后续设计的指导原则。

### 4.1 如果把人脑建模成 AI Agent

```
睡眠 → 醒来(Day Tick) → 恢复Self/Goals/OpenLoops/环境 → 进入事件循环 → 晚上睡觉(Sleep Tick) → 写回长期记忆
```

一天 = 一个 Day Tick → N 个 Event Loop → 一个 Sleep Tick。Tick 内不是一直推理：

```
while (awake) {
    感知()
    更新内部状态()
    如果需要思考 → 推理()
    行动()
}
```

### 4.2 映射到代码

| 人脑节律 | AI 实现 | 当前状态 |
|:---------|:--------|:---------|
| **醒来 → 恢复 Self/Goals/Open Loops/环境** | Day Tick — 读 `prompts/identity/*.md` ✅ + Python 管理器 ✅ + `_scan_environment()` ✅ | ✅ 已实现 |
| **→ 形成初始 Working Memory** | Day Tick — `replace_working_memory()` ✅ | ✅ 已实现 |
| **Alive: 感知** | `_perceive()` — diff 检测 idle/seq/period/date | ✅ 已实现 |
| **Alive: NeedReasoning?** | `_need_reasoning()` — 用户消息 / rest≥3 / WM 变化 / 紧急 concern | ✅ 已实现 |
| **Alive: LLM 推理** | `AutonomousMind.tick()` — 内循环 use_tool → think/speak/rest | ✅ 已实现 |
| **睡前：沉淀+清空** | Sleep Tick — `_enqueue_consolidation()` ✅ + `clear_working_memory()` ✅ | ✅ 已实现 |

### 4.3 Prompt 装配器模型（Context Assembler）

人脑每 Tick 实时构建的 Prompt 并非固定模板，而是：

```
Self               → "我是志远"
Current World      → "我现在在公司"
Current Attention  → "今天下午要开会"
Current Goals      → "还有 Bug 没修"
Current Emotion    → "有点焦虑"
Working Memory     → "要不要继续写代码？"
Need               → "同事问：这个什么时候好？"
```

**长期记忆（昨天/前天/去年）不会进入当前上下文。** Working Memory 才是真正的 Prompt。

### 4.4 Attention 是替换/删除/重排，而非追加

所有刺激（声音/光/手机/肚子饿/Bug/老板）→ **竞争** → 只有几个进入 Working Memory：

```
Working Memory:
  - 老板（高优先级）
  - Bug（高优先级）
  - 会议（持续关注）
```

其他全部被忽略。**Prompt 不是越来越长，而是不断替换、删除、重排。**

### 4.5 已实现的节律点

| 节律 | 实现 | 状态 |
|:-----|:------|:------|
| **Day Tick**（醒来仪式） | `scheduler._day_tick()` — 读身份文件 + 管理器 + 环境 → WM | ✅ 已实现 |
| **Sleep Tick**（睡前仪式） | `scheduler._sleep_tick()` — consolidation + 清空 WM | ✅ 已实现 |

这两个节点都不调 LLM，纯调度层状态管理。见 §二 详细设计。

### 4.6 与现有代码的映射

| 你描述的概念 | 已有代码 | 文件 |
|:------------|:---------|:-----|
| **Self** | `prompts/identity/self.md` + `SelfModelManager` | `prompts/identity/` + `state/self_model.py` |
| **Current World** | `_build_context()` → idle_seconds / time_of_day | `autonomous_mind.py` |
| **Attention** | `ConcernManager` → `all_effective(3)` | `state/concerns.py` |
| **Goals** | `prompts/identity/goals.md` + `GoalManager` | `prompts/identity/` + `state/goals.py` |
| **Emotion** | `last_thought` 中自然表达（无独立字段） | `autonomous_mind.py` |
| **Working Memory** | `WorkingSetManager`（6h TTL）+ AutonomousMind 内循环积累 | `state/working_set.py` + `autonomous_mind.py` |
| **Context Assembler** | `AutonomousMind._build_context()` | `autonomous_mind.py` |
| **NeedReasoning** | `_should_skip_llm()`（只有 rest 跳过，无条件触发） | `autonomous_mind.py` |

### 4.7 未满足的设计目标

| 目标 | 现状 | 差距 |
|:-----|:-----|:------|
| Day Tick → 初始 Working Memory | ✅ 已实现 | `scheduler._day_tick()` 读身份文件 + 管理器 + 环境 |
| Alive Tick: 感知→NeedReasoning?→决策 | ✅ 已实现 | `_perceive()` + `_need_reasoning()` + 内循环 |
| NeedReasoning? 门 | ✅ 已实现 | 条件：用户消息 / rest≥3 / WM 变化 / 紧急 concern |
| Working Memory 作为 prompt 核心骨架 | ⚠️ 部分 | WM 已实现在 stream 中，但 LLM 的 prompt 尚未以 WM 为核心编排 |
| Prompt 替换而非追加 | ⚠️ 部分 | 意识流每次重新构建，但 history 仍在追加 |

---

## 五、优先修复清单

### P0：旧系统遗留修复（pending_expression 仍可能被 internal_state section 调用）

| 修复 | 改动位置 | 改动量 | 效果 |
|:-----|:---------|:-------|:-----|
| `_topic_recently_expressed` 检查最近 10 条而非 1 条 | `state/pending_expression.py` L254 | 1 行 | 旧路径备用时减少重复 |

### P1：待完成项

| 内容 | 说明 | 优先级 |
|:-----|:------|:-------|
| `autonomous_mind.md` prompt 工具列表补 `write_file` | 当前 AI 不知道可用 `write_file` 修改身份文件 | 🔴 高 |
| Concern 表达次数衰减 | 已表达 N 次的 concern 自动降权，避免多次 speak 同一话题 | 🟡 中 |
| 意识流 prompt 注入最近 5 条输出全文 | 当前 `already_said` 仅 4 条×80 字符，可能不够 AI 判断重复 | 🟡 中 |

### P2：增强感知能力

`_perceive()` 已实现基本的 diff 检测（idle/seq/period/date），可扩展更多感知维度：

```python
def _perceive(self, life_state) -> dict:
    signals = {}
    # 已有：idle_seconds 变化、output.json 新 seq、时段变化、日期变化
    # 可扩展：
    signals["user_message"] = self._check_new_message()
    signals["time_change"] = self._check_time_change()
    signals["system_event"] = self._check_events()
    return signals
```

| 影响 | 说明 |
|:-----|:------|
| 提高感知灵敏度 | 更多感知维度 → 更精确的 NeedReasoning? 判定 |
| 实现位置 | `autonomous_mind.py` 的 `_perceive()` 方法 |

### P3：长期方向

| 内容 | 说明 |
|:-----|:------|
| `final_reply.md` schema 落地为校验 | 当前 `final_reply.md` 是纯文档，可考虑作为 `reply_strategy` 的 JSON schema 校验落地 |
| Prompt 体系压缩 | 随着旧系统弃用，合并 `brain_judge_idle.md` 等冗余 prompt 文件 |
| WorkingSetManager 与意识流 WM 融合 | 当前 `WorkingSetManager`（6h TTL）与意识流 `working_memory` 字段是两套，考虑合并 |
