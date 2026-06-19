# 大脑后台意识系统

## 一、项目目标

- **项目名称**：大脑后台意识系统
- **一句话描述**：把人脑的认知循环映射为模块化的后台守护线程，让 AiBrain 拥有持续的"意识流"——不是等用户触发才活动，而是像生物一样一直在"活着"。
- **核心目标**：
  1. 构建一个模块化的大脑认知循环，持续在后台运行
  2. 每个模块对应一个脑功能：感知→注意力→记忆→预测→情绪→目标→执行→行动→学习
  3. 模块之间通过共享状态（internal_state.json）通信，各自有独立的更新频率
  4. 最终让"自我"成为这个循环持续运行时自然生成的叙事界面
- **不做的事**：
  - 不重写 memory/ 或 state/ 核心（只在其上构建循环）
  - 不改变 chat 主流程（循环在独立 daemon 线程运行）
  - 不追求"真正的意识"——这是一个实用主义的功能模拟

## 二、业务背景

- **问题现状**：
  - 目前大脑是碎片化的：_proactive_loop（120s）、agent_loop（45s）、_try_proactive_send（聊天后），各跑各的，没有统一架构
  - 没有独立情绪系统——mood 只是 self_narrative 里的被动标签，不会自主变化
  - 没有注意力调度——系统不分轻重缓急，所有 concern 等权重
  - 没有预测机制——大脑只在"事后"反应，不会主动预判
  - 没有学习更新闭环——对话完了就完了，不会有"刚才那句话让我改变了什么"
  - 这些碎片缺少一个统一的认知框架来组织

- **设计参考**：人脑认知循环

```text
while alive:
    sensory_input = 感官输入 + 身体状态
    salience = 注意力系统判断什么重要
    memory_context = 工作记忆 + 长期记忆检索
    prediction = 大脑根据经验预测接下来会发生什么
    error = 现实输入 - 预测
    emotion = 身体/价值系统给出优先级和意义
    plan = 前额叶做目标选择和行动规划
    action = 语言、动作、抑制、想象、内心独白
    learning = 根据结果更新模型
```

- **关键洞察**："自我"不是某个模块，而是这个循环持续运行时，给自己生成的一个稳定叙事界面。

## 三、功能需求

### 模块映射

| 脑功能 | 模块名 | 对应现有系统 | 新增 |
|--------|--------|-------------|------|
| 感知输入 | sensory_input | workmemory.input / chat 消息 | 内部状态信号（时间、情绪自身变化） |
| 注意力 | attention | concerns（激活/衰减） | 优先级调度器，决定"当前 CPU 给谁" |
| 工作记忆 | working_memory | output.json / package.json | 增强上下文持有 |
| 长期记忆 | long_term_memory | Qdrant + graph | 后台联想漫步 |
| 预测 | prediction | — | **新增**：LLM 预测对话走向 |
| 情绪 | emotion | self_narrative.mood | **新增**：VAD 三维自主漂移 |
| 目标 | goal_system | goals（state/store） | 短期目标动态管理 |
| 执行控制 | executive | pick_to_send | 选择/抑制/切换机制 |
| 行动输出 | action_output | pending_expression + output | 内心独白三级分层 |
| 学习 | learning | daily_reflect / dedup | 更频繁的微调更新 |

### P0 功能（第一阶段必须）

| 功能 | 说明 |
|------|------|
| 情绪自主漂移 | VAD 三维模型，高频 tick 漂移，持久化，无需 LLM |
| 注意力调度器 | 根据 salience 决定关注优先级，控制其他模块的触发 |
| 感知输入层 | 收集外部（用户消息）+ 内部（时间、情绪状态）信号 |
| 认知循环框架 | 模块化调度器，各模块按各自频率运行 |
| 前端情绪展示 | 聊天界面显示猫猫当前情绪（情绪标签） |

## 四、非功能需求

- **性能**：纯数学模块（情绪、注意力）≤ 10ms；LLM 模块（预测、学习）不抢占对话资源
- **可靠**：所有模块 daemon=True，异常只 log 不抛；state 损坏时回滚默认值
- **可观测**：每个模块运行状态可查询（通过扩展 /chat/state 接口）
- **可扩展**：新增模块只需实现 tick() 接口 + 注册到 loop

## 五、系统架构

### 认知循环架构（8 层）

```
Input ──→ Perception ──→ Attention ──→ Memory
  ↑                                          │
  │                                          ▼
  │                                       State
  │                                          │
  │                                          ▼
  │                                    Cognition
  │                                          │
  │                                          ▼
  │                                  Expression / Action
  │                                          │
  │                                          ▼
  │                                  Learning / Update
  └──────────────────────────────────────────┘
                   反馈闭环
```

**每层的职能：**

| 层 | 对应模块 | 现有关联 | 频率 |
|----|---------|---------|------|
| **Input** | `main_brain/input/` | chat_routes → InputEvent | 事件驱动 |
| **Perception** | `main_brain/perception/` | (当前无，待建) | ~30s |
| **Attention** | `main_brain/attention/` | concerns (现有) | ~30s |
| **Memory** | `modules/brain/memory/` | Qdrant + graph + workmemory | ~3min |
| **State** | `modules/brain/state/` | internal_state.json | 持续 |
| **Cognition** | `main_brain/cognition/` | pending_expression (部分) | ~3min |
| **Expression** | `main_brain/expression/` | output + proactive_send | ~3min |
| **Learning** | `main_brain/learning/` | daily_reflect + dedup | ~15-60min |

### 目录结构

```
backend/main_brain/
  input/              # 1. 输入层：统一 InputEvent + Router
  perception/         # 2. 感知层：(待建) 意图/实体/情感提取
  attention/          # 3. 注意力层：(待建) salience 调度
  memory/             # 4. 记忆层：(规划迁移 modules/brain/memory)
  state/              # 5. 状态层：(规划迁移 modules/brain/state)
  cognition/          # 6. 认知层：(待建) 思考/推理/规划
  expression/         # 7. 表达层：(待建) 行动输出
  learning/           # 8. 学习层：(待建) 巩固/反思/更新
```

每层一个独立目录，每层有独立的 __init__.py 做模块转发。层之间通过共享状态通信，不直接调用。

### 关键设计决策

1. **模块化而非单一大循环**：每个模块有独立的 tick() 接口，loop.py 只负责轮询和调度，不关心各模块内部逻辑
2. **通过共享状态通信而非直接调用**：防止循环依赖，解耦
3. **分频次运行**：高频模块（情绪/注意力/感知）每 30s，避免过度开销；中频（记忆/预测/目标/执行/行动）每 3min；低频（学习）每 15-60min
4. **"自我"是涌现产物**：不单独实现一个"自我模块"，而是让循环本身自然产生叙事连续性
5. **替换而非并存**：新 subconscious 完全替代 _proactive_loop 和 agent_loop

## 六、数据结构

### internal_state.json 新增字段

```json
{
  "emotion": {
    "valence": 0.0,      // -1~1
    "arousal": 0.3,      // 0~1
    "dominance": 0.5,    // 0~1
    "last_drift_at": "",
    "decay_rate": 0.05,
    "volatility": 0.15
  },
  "attention": {
    "focus": "",          // 当前关注的焦点实体
    "salience_map": {},   // {实体名: salience分数}
    "last_shift_at": ""
  },
  "sensory": {
    "last_user_message_at": "",
    "last_internal_tick_at": "",
    "idle_hours": 0.0
  },
  "prediction": {
    "last_prediction": "",
    "last_error": 0.0,
    "confidence": 0.5
  },
  "goals": {
    "active": [],
    "completed": []
  },
  "subconscious": {
    "tick_counts": {},
    "last_module_times": {}
  }
}
```

### 内心独白日志（inner_monologue.jsonl）

```
{"ts":"...","text":"...","level":"internal|seed|send","mood":"...","trigger":"...","emotion":{"v":0.0,"a":0.3,"d":0.5}}
```

## 七、流程设计

### 认知循环主流程

```
loop():
  while running:
    now = time()
    for each module in registered_modules:
      if now - module.last_tick >= module.interval:
        module.tick(shared_state)
        module.last_tick = now
    sleep(15s)
```

### 各模块 tick() 逻辑

**sensory_input.tick()** (~30s)：
```
1. 检查距上次用户消息的时间 → 更新 idle_hours
2. 读取当前情绪状态 → 作为内部信号
3. 写入 sensory 字段
```

**attention.tick()** (~30s)：
```
1. 从 concerns 读取当前所有实体
2. 按 effective × emotion_bias 计算 salience
3. 选最高 salience 作为 focus
4. 写入 attention 字段
```

**emotion.tick()** (~30s)：
```
1. VAD 随机漫步 + decay 向中性回归
2. 如果有关注焦点，向该记忆的平均 affect 方向弱漂移
3. 写入 emotion 字段
4. log 情绪变化
```

（其余模块后续阶段实现）

## 八、API 设计

**无新增 HTTP API。** 现有 `/chat/state` 接口扩展返回：

```
GET /chat/state → 原返回值扩展:
  + emotion: {valence, arousal, dominance, mood_label}
  + attention: {focus, salience_top}
```

**前端新增展示：**
- 情绪标签显示在聊天窗口角落
- 内心独白以灰色 💭 气泡出现在对话流中

## 九、验收标准

| # | 验收项 | 预期 |
|---|--------|------|
| 1 | 认知循环启动 | 启动后 log 显示各模块定期 tick |
| 2 | 情绪漂移 | 30s 后 emotion 数值变化，持久化 |
| 3 | 注意力调度 | attention.focus 有值，随时间变化 |
| 4 | 前端展示 | 聊天界面出现情绪标签 |
| 5 | 模块隔离 | 一个模块挂掉不影响其他模块 |

## 十、开发任务拆分

### 第一阶段：认知循环框架 + 基础模块

| ID | 任务 | 复杂度 | 文件 |
|----|------|--------|------|
| T001 | 创建 subconscious/ 模块骨架 | S | `__init__.py`, `loop.py`, `CLAUDE.md` |
| T002 | 实现情绪系统 emotion.py | M | `emotion.py` |
| T003 | 实现感知输入层 sensory_input.py | S | `sensory_input.py` |
| T004 | 实现注意力调度 attention.py | M | `attention.py` |
| T005 | state/store.py 加新字段 + version 6 | S | `store.py` |
| T006 | app.py 集成 start_subconscious() | S | `app.py` |
| T007 | 替换 agent_loop | S | 移除旧启动 |
| T008 | 前端情绪标签展示 | M | `web/src/` |

### 后续阶段

| 阶段 | 模块 | 依赖 |
|------|------|------|
| 二 | prediction, goal_system, executive | T001-T006 |
| 三 | action_output（内心独白） | 二 |
| 四 | learning（记忆巩固） | 二+三 |
