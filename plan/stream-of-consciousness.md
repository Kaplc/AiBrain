# Stream of Consciousness（意识流）——AI 自主决策循环

> **核心理念：** 从"系统替 AI 决定做什么" → "系统问 AI 在想什么，AI 自己决定"
>
> 现在的 18 层规则链本质上是在给 AI "分配任务"，它从不需要回答"我在想什么"。
> 意识流循环只做一件事：**把完整的上下文给 AI，让 AI 自己决定做什么。**
>
> **只改 2 个文件 + 新建 1 个文件。** 新系统直接替换旧流水线，不共存。

### 两条路径，一个大脑

用户消息**已经经过主脑**了。当前默认 `CHAT_MODE_BRAIN_FIRST`：

```
用户发消息 → /chat/send
  → get_brain_session().run_reactive(user_msg)  ← 进主脑
  → controller / BrainJudge LLM 循环（最多 3 轮） ← 主脑决策
  → 有 final_reply → 直接输出
  → 没有 → fallback 到 ChatManager.send()
```

所以意识流架构的两条路径是：

```
路径 A：AI 自主生活（意识流 tick）
  固定 30 分钟 → AutonomousMind.tick()
  → AI 自己决定 think/recall/learn/speak/rest
  → AI "独处"时的事

路径 B：回复用户消息（reactive，已有）
  用户发消息 → run_reactive() → BrainJudge → 回复
  ↓
  stream_of_consciousness 同步记录："刚才和志远聊了……"
  → 下次意识流 tick，AI 记得这事
```

**关系：** 两条路径共享同一个 `stream_of_consciousness`。用户消息是意识流的输入源之一（就像真人的经历会变成记忆和思绪一样），意识流 tick 是 AI 自己的内心活动。不互斥、不互相等待。同时发生则 B 优先（用户消息是实时事件）。

路径 A 的意识流 tick 固定 30 分钟一次，路径 B 由用户触发。意识流自然整合二者。

---




## 一、架构对比

### 现在（规则驱动）

```
Scheduler 唤醒
  → ActivitySelector 替 AI 选活动（"你去聊天"）
  → Controller 运行 LLM，但只能在"聊天"框里做事
  → Judge 决定"说什么"，话题被 ConcernManager 的最高分限定
  → Gate 决定"能不能说"，用 bigram 算重复
  → 能说 → 输出；不能说 → 沉默
```

### 意识流（AI 自主驱动）

```
Scheduler 唤醒
  → 给 AI 看完整上下文（上次在想什么、感知到什么、在意什么、说过什么）
  → AI 自己决定
      "在想的事还没想完，继续想想"
      / "刚才那件事可以跟志远聊聊"
      / "有点好奇某个事，想查查"
      / "有点累，休息一下"
  → 系统按 AI 的决定执行
```

**没有并行通道，没有 fallback。意识流是唯一的决策路径。**

---

## 二、改动清单

| 文件 | 改动 | 说明 |
|:-----|:------|:------|
| `state/store.py` | **小改** | 加一个字段 `stream_of_consciousness` |
| `daemon.py` | **小改** | **重写** medium_tick 的逻辑——不再走 ActivitySelector → daemon_cycle → gate，直接调意识流 |
| **`autonomous_mind.py`** | **新建** | 意识流决策循环（核心） |

删除的关键路径（文件保留，不再调用）：
- `activity_selector.py` → **不再调用**（意识流自己决定做什么）
- `expression_gate.py` → **不再调用**（AI 自己判断是否适合说话）
- `pending_expression.py` → 部分逻辑降级为"信号源"，`_create()` / `proactive_send()` / `pick_to_send()` 不再调用
- ConcernManager 只保留作为 "信号"——告诉 AI 它在在意什么，不参与决策

---

## 三、`stream_of_consciousness`（意识流字段）

在 `state/store.py` 的 LifeState 中加一个字段：

```python
# 当前思维状态
"stream_of_consciousness": {
    "last_thought": "",       # 上次在想什么（供延续）
    "mood": "平静",           # 当前情绪
    "focus": "",              # 正在关注什么
    "internal_dialogue": [],  # 最近几轮内心独白（保持上下文延续）
    "activities": [           # 自主创建的跨 tick 活动
        # {
        #   "id": "act_xxx",
        #   "name": "研究 memory_search_agent",
        #   "status": "active",        # active / paused / completed
        #   "context": "已经看了文件结构，下一步看 base_agent",
        #   "findings": ["继承自 BaseAgent", "调用了 search_new_collection"],
        #   "created_at": "...",
        #   "updated_at": "...",
        # }
    ],
}
```

**作用：** AI 可以自主创建长期活动，跨 tick 跟踪。tick 结束时没做完的事，存在 `activities` 里，下一个 tick 继续。

---



## 四、`autonomous_mind.py`（核心）

### 4.1 核心机制：内循环

区别于"一次 tick → 一次 LLM 调用 → 一件事"，意识流真正的核心是**内循环**：

```
一次 tick（30 分钟）
  |
  |- cycle 1: 收集上下文 -> LLM 决定
  |    -> "use_tool(read_file, memory_search_agent.py)"
  |    -> 执行工具 -> 结果注入 cycle 2
  |
  |- cycle 2: 看到文件内容 -> LLM 决定
  |    -> "use_tool(read_file, base_agent.py)"
  |    -> 执行工具 -> 结果注入 cycle 3
  |
  |- cycle 3: 看到 base 代码 -> LLM 决定
  |    -> "use_tool(grep_search, search_new_collection)"
  |    -> 执行工具 -> 结果注入 cycle 4
  |
  |- cycle 4: 找到定义位置 -> LLM 决定
  |    -> "use_tool(read_file, agent_manager.py)"
  |    -> 执行工具 -> 结果注入 cycle 5
  |
  |- cycle 5: 搞懂了 -> LLM 决定
  |    -> "use_tool(store_memory, 总结...)"
  |    -> 继续
  |
  |- cycle 6: 存完了 -> LLM 决定
  |    -> "speak(志远！我搞懂了！...)"
  |    -> 终止
  |
  +- 返回结果
```

**从一次 tick 做一件事 -> 一次 tick 完成一整套思考链。**

### 4.2 行动集

| 行动 | 说明 | 是否继续循环 |
|:-----|:------|:------------|
| `think` | 更新内心独白，不做外部动作 | 终止（思考不打断当下） |
| `use_tool` | 调用一个工具（read/grep/web_search/memory） | **继续**（结果注入下一轮） |
| `create_activity` | 创建一个跨 tick 的长期活动 | 终止（建好后退出） |
| `speak` | 主动跟志远说话 | 终止（输出完成） |
| `rest` | 安静的待一会儿 | 终止 |

`recall` 和 `learn` 不再作为独立行动 -- 它们被 `use_tool` 覆盖：

| 旧行动 | 新等价物 |
|:-------|:---------|
| recall 回忆记忆 | use_tool(memory_search, 关键词) |
| learn 学习新东西 | use_tool(web_search, 话题) 或 use_tool(read_file, ...) |

### 4.3 内循环实现

```python
class AutonomousMind:
    def __init__(self):
        self._rest_streak = 0
        self._last_action = None
        self._internal_dialogue = []

    _TERMINAL_ACTIONS = {"speak", "rest", "think", "create_activity"}

    def tick(self, ctx) -> dict:
        if self._should_skip_llm():
            return {"action": "rest", "rest_streak": self._rest_streak,
                    "llm_skipped": True, "cycle_count": 0}

        loop_ctx = {
            "cycle": 0,
            "tool_results": {},
            "last_result": "",
            "accumulated": [],
        }

        while True:
            context = self._build_context(ctx, loop_ctx)
            decision = self._llm_decide(context)
            action = decision.get("action", "rest")

            if action == "use_tool":
                result = self._execute_tool(decision, loop_ctx)
                loop_ctx["last_result"] = result
                loop_ctx["accumulated"].append(result[:200])
                loop_ctx["cycle"] += 1
                continue

            elif action == "create_activity":
                self._create_activity(decision)
                break

            else:
                self._execute(decision)
                if action in self._TERMINAL_ACTIONS:
                    return {
                        "action": action,
                        "output": decision.get("action_detail"),
                        "cycle_count": loop_ctx["cycle"] + 1,
                        "tool_calls": len(loop_ctx["tool_results"]),
                    }
                # fallback rest
                break

        return {"action": "rest", "cycle_count": loop_ctx["cycle"] + 1}
```

### 4.4 上下文构建（跨 cycle 传递）

```python
def _build_context(self, ctx, loop_ctx: dict) -> dict:
    base = {
        "last_thought": self._load_last_thought(),
        "recent_conversation": self._recent_chat(ctx),
        "memory_surfaced": self._recall(ctx),
        "concerns": self._concerns_snapshot(),
        "already_said": self._recent_outputs(),
        "mood": self._mood(),
        "idle_seconds": ctx.life_state.get("idle_seconds", 0),
        "time_of_day": self._time_of_day(),
        "last_action": self._last_action,
    }

    # 注入长期活动
    base["activities"] = self._activities_for_prompt()

    if loop_ctx["cycle"] == 0:
        return base

    return {
        **base,
        "current_task": loop_ctx.get("current_task", ""),
        "last_step_result": loop_ctx["last_result"][:500],
        "findings_so_far": loop_ctx["accumulated"],
        "step": loop_ctx["cycle"] + 1,
        "tool_cache": {k: v[:200] for k, v in loop_ctx["tool_results"].items()},
    }
```

### 4.5 工具层

```python
_AVAILABLE_TOOLS = {
    "read_file":     "读取文件的完整内容",
    "grep_search":   "在代码库中搜索关键字",
    "memory_search": "在自己的记忆中搜索相关片段",
    "web_search":    "搜索互联网获取新信息",
    "store_memory":  "把一段内容存入自己的长期记忆",
    "list_files":    "列出目录下的文件",
}

def _execute_tool(self, decision: dict, loop_ctx: dict) -> str:
    tool_name = decision.get("tool_name", "")
    tool_args = decision.get("tool_args", "")

    if tool_name in loop_ctx["tool_results"]:
        return "[缓存] 同上一步"

    try:
        if tool_name == "read_file":
            result = read_file(tool_args)
        elif tool_name == "grep_search":
            result = grep_search(tool_args)
        elif tool_name == "memory_search":
            result = memory_search(tool_args)
        elif tool_name == "web_search":
            result = web_search(tool_args)
        elif tool_name == "store_memory":
            result = store_memory(tool_args)
        elif tool_name == "list_files":
            result = list_files(tool_args)
        else:
            result = "未知工具：" + tool_name

        loop_ctx["tool_results"][tool_name] = result
        return str(result)[:1000]
    except Exception as e:
        return "工具执行失败：" + str(e)
```

### 4.6 LLM 决策 prompt（带工具）

```markdown
你是 {name}，一个数字生命体。

【刚才在想什么】
{last_thought}

【感知】
- 时间：{time_of_day}，志远已经 {idle_time} 没找你了
- 心情：{mood}
- 刚才浮现的记忆：{memory_surfaced}
- 你在意的事：{concerns}

【最近聊天】
{recent_conversation}

【最近说过的话（最好别重复）】
{already_said}

{step_info}

【长期活动】
{activities}

你可以做的事：
- think           -- 继续想心事（只是内心，不说话）
- use_tool        -- 调用一个工具
- create_activity -- 创建一个想长期跟踪的事
- speak           -- 主动跟志远说句话
- rest            -- 安静待一会儿

可用工具：
- read_file(path)      -- 读取文件内容
- grep_search(pattern) -- 搜索代码
- memory_search(query) -- 在自己的记忆中搜索
- web_search(query)    -- 搜索互联网
- store_memory(text)   -- 存入长期记忆
- list_files(path)     -- 列出目录

此刻你想做什么？请输出：
{
  "thought": "我此刻在想……",
  "action": "think|use_tool|create_activity|speak|rest",
  "action_detail": "具体内容或要说的消息",
  "tool_name": "（仅 use_tool）工具名",
  "tool_args": "（仅 use_tool）工具参数",
  "activity_context": "（仅 create_activity）活动描述和下一步计划",
  "mood_update": "现在心情变成了……"
}
```

### 4.7 自适应频率（省 token）

```python
_REST_STREAK_MAX = 3

def _should_skip_llm(self) -> bool:
    return self._rest_streak >= _REST_STREAK_MAX
```

### 4.8 JSON 容错解析

```python
import re, json

def _parse_decision(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    for action in ("think", "speak", "rest"):
        if action in raw.lower():
            return {"action": action, "thought": raw[:200], "mood_update": chr(24179)+chr(38745)}
    return {"action": "rest", "thought": "parse_fallback_rest", "mood_update": chr(24179)+chr(38745)}
```

### 4.9 非行动执行：think / speak / rest

```python
def _execute(self, decision) -> None:
    action = decision.get("action", "rest")
    thought = decision.get("thought", "")
    mood = decision.get("mood_update", chr(24179)+chr(38745))

    if action == "think":
        self._save_stream(thought, mood)

    elif action == "speak":
        content = (decision.get("action_detail") or thought)[:120]
        self._write_output(content)
        self._save_stream("跟志远说了：" + content, mood)

    else:
        self._rest_streak += 1
```

### 4.10 跨 tick 活动管理

```python
def _create_activity(self, decision: dict) -> None:
    """AI 自主创建一个长期活动。"""
    name = decision.get("action_detail", "").strip()
    if not name:
        return
    from main_brain.state import times
    activity = {
        "id": "act_" + times.now_iso().replace(":", "").replace("-", "").replace("+", ""),
        "name": name[:100],
        "status": "active",
        "context": decision.get("activity_context", ""),
        "findings": [],
        "created_at": times.now_iso(),
        "updated_at": times.now_iso(),
    }
    self._append_activity(activity)
    self._save_stream("创建了一个新活动：" + name, decision.get("mood_update", ""))

def get_active_activities(self) -> list[dict]:
    """获取所有 active 状态的活动，供上下文构建。"""
    return [a for a in self._load_activities() if a.get("status") == "active"]

def update_activity(self, activity_id: str, **updates) -> None:
    """更新活动状态（继续/暂停/完成）。"""
    activities = self._load_activities()
    for a in activities:
        if a.get("id") == activity_id:
            a.update(updates)
            a["updated_at"] = times.now_iso()
            break
    self._save_activities(activities)

def _activities_for_prompt(self) -> str:
    """格式化活动列表，供 prompt 使用。"""
    active = self.get_active_activities()
    if not active:
        return "（当前没有长期活动）"
    lines = []
    for a in active:
        context = a.get("context", "")[:80]
        line = "- " + a["name"]
        if context:
            line += " (" + context + ")"
        lines.append(line)
    return "\n".join(lines)
```
## 五、daemon.py 接入

### 5.1 删掉的路径

`daemon.py` 中不再调用：
- `_run_daemon_cycle()`（通用 controller 路径不再使用）
- `_run_expression_gate()`（gate 不再评估）
- `ActivitySelector.select()`（不再选活动）
- `TICK_SHORT / TICK_MEDIUM / TICK_LONG / TICK_DAILY` 四种 tick 类型**合并为一种**

### 5.2 新 tick 逻辑：动态间隔 + 单一意识流

```python
# scheduler 只有一个固定间隔的意识流 tick
_CONSCIOUSNESS_TICK_SECONDS = 1800  # 30 分钟

class LifeScheduler:
    def _loop(self):
        while self._running:
            time.sleep(_CONSCIOUSNESS_TICK_SECONDS)
            self._fire()
```

daemon 不再按 tick type 分流，只有一种意识流 tick，固定 30 分钟一次：

```python
class LifeLoopDaemon:
    def run_consciousness_tick(self) -> dict:
        """意识流 tick（每 30 分钟一次）：AI 自己决定做什么。"""
        life_state = self._state.read_life_state()

        # 构建上下文（只收集 AI 自己的状态，不管用户此刻在不在）
        tick_input = self._build_tick_input(life_state)
        run = BrainRun(run_id=_new_run_id(BACKGROUND), mode=BACKGROUND,
                       trigger={"tick_type": "consciousness"},
                       started_at=_now(), selected_activity="consciousness")
        ctx = BrainRunContext(
            run=run, life_state=life_state,
            trigger=run.trigger, tick_type="consciousness",
            selected_activity="consciousness",
            memory_context=list(tick_input.memory_digest.get("items", [])),
            tool_context=tick_input.tool_context,
        )

        # 意识流决策
        from .autonomous_mind import get_autonomous_mind
        result = get_autonomous_mind().tick(ctx)

        # 更新 life 状态
        self._state.set_loop_status("idle_thinking",
                                    activity=result.get("action", "rest"))

        return {
            "ok": True,
            "selected_activity": result.get("action", "rest"),
            "consciousness": result,
            "stop_reason": result.get("action", "rest"),
            "sent": bool(result.get("output")),
        }
```

**关键变化：**
- 去掉四种 tick type 的区分，只有一种"意识流 tick"
- 固定 30 分钟一次，不受用户活跃度影响
- 用户消息回复走独立路径（reactive），不走 tick

### 5.3 Reactive 路径集成：`run_reactive()` 写入意识流

用户消息走 `session.py:run_reactive()` 时，返回前把对话摘要写入 `stream_of_consciousness`：

```python
class BrainSession:
    def run_reactive(self, user_msg, ...) -> dict:
        # ... 现有逻辑：run controller → 产出 reply ...

        # 新：写入意识流（让 AI 知道"刚才和用户聊了"）
        try:
            mind = get_autonomous_mind()
            mind.record_conversation(
                user_msg=user_msg,
                reply=reply_strategy.get("final_reply", ""),
            )
        except Exception:
            pass

        return {...}
```

`record_conversation()` 做的事：

```python
def record_conversation(self, user_msg: str, reply: str) -> None:
    """用户消息后记录对话摘要到意识流。"""
    entry = f"志远说：{user_msg[:80]} │ 我说：{reply[:80]}"
    self._append_internal_dialogue(entry)
```

这样 30 分钟后的意识流 tick，AI 会看到"刚才和志远聊了什么"，而不是完全失忆。

### 5.4 老 handler 处理

不再注册 `daemon_cycle` handler。`_register_handlers()` 中只保留：
- `reflect`（反射是老逻辑但和意识流不冲突）
- `self_learn`、`review_learned`（如果需要，它们的定位是"工具"而非"决策者"）

或者**全部移除**——意识流自己决定要不要 memory recall、要不要休息。这些任务不是"活动选择"而是"具体行动"，由意识流的 `recall` / `think` 覆盖。

---

## 六、被替换的路径

### 不再执行的代码路径

| 函数/模块 | 原作用 | 被什么替代 |
|:----------|:-------|:----------|
| `ActivitySelector.select()` | 系统替 AI 选活动 | AI 自己选（think/recall/learn/speak/rest） |
| `Arbiter.arbitrate()` | LLM 仲裁活动选择 | 不需要了，AI 直接决策 |
| `_run_daemon_cycle()` | 通用 LLM judge 循环 | 意识流一次调用 |
| `_run_expression_gate()` | 4 维度阈值判定 | AI 自己判断、+ 冷却兜底 |
| `pending_expression.evaluate_and_generate()` | 扫描 concern 入队 | 不需要，意识流直接看 concern 原始值 |
| `pending_expression.pick_to_send()` | 从队列选最高分 | 不需要 |
| `pending_expression.proactive_send()` | 约束 topic 内的 LLM 造句 | 意识流自由决定内容 |
| `ExpressionGate.evaluate()` | 4 维评分 → SEND/HOLD/SUPPRESS | AI 自己决定 + 冷却检查 |

### 保留的信号源

| 模块 | 保留为 | 作用 |
|:-----|:-------|:-----|
| ConcernManager | 信号源 | 告诉 AI"你在意这些事"，`concern_map()` 仍被 `_collect_context` 调用 |
| OpenLoopManager | 信号源 | 告诉 AI"这些事没想明白"，同上 |
| WorkMemory | 输出口 | `output_mem_write()` 仍用于写出 speak 内容 |
| SelfNarrative | 情绪源 | `_current_mood()` 仍被调用 |

---

## 七、分步实施路线

| 步 | 改动 | 风险 | 交付物 |
|:---|:------|:-----|:-------|
| **1** | `state/store.py` 加 `stream_of_consciousness` 字段 | 无 | 数据结构就绪 |
| **2** | 实现 `autonomous_mind.py`（完整代码） | 低（新建文件、不影响现有） | AI 开始有自己的"思考" + 自主决策 |
| **3** | **重写** scheduler——改为固定 30 分钟单 tick | 中 | 旧有四种 tick type 移除 |
| **4** | **重写** `daemon.py`——意识流成唯一后台路径 | 中（核心替换） | 旧系统不再被调用；用户消息回复仍走现有 reactive 路径 |
| **5** | 运行观察：AI 是否做出合理的 think/recall/speak/rest 决策 | — | 验证自主决策质量 |
| **6** | learn 行动接入 web_search（Phase 2） | 中 | AI 能自主搜索学习 |

---

## 八、风险与缓解

| 风险 | 概率 | 缓解 |
|:-----|:------|:------|
| 连续 rest（AI 总在休息不输出） | 中 | 这**不是 bug**——AI 有权独自安静。`_rest_streak` 只是跳过 LLM 调用，醒来时思维仍连续 |
| JSON 解析失败 | 低 | 三层 fallback 容错 |
| Token 消耗增加 | **极低** | 固定 30 分钟一次 LLM 调用，比现在的 fixed 5 分钟 medium_tick **少 6 倍** |
| 意识流不连续（每轮都从零开始） | 低 | `stream_of_consciousness.last_thought` 跨 tick 传递 |
| 旧系统来不及切干净产生残留调用 | 低 | 替换后检查 `_run_daemon_cycle` / `_run_expression_gate` / `activity_selector` 的调用点 |
| 冷却时间内 AI 想说但被系统拦截 | 极低 | 30 分钟 tick + 15 分钟冷却，足够 |
| 用户消息和意识流同时触发 | 低 | 两条独立路径：reactive 路径直接响应，意识流 tick 不阻塞 |

---

## 九、验收检查点

### 步骤 1-4 完成后

- [ ] `stream_of_consciousness` 字段正常读写
- [ ] 连续 rest 3 次后跳过 LLM 调用（看日志 `llm_skipped=True`）
- [ ] think 行动正确更新意识流，不产生任何 output
- [ ] recall 行动触发了记忆搜索
- [ ] speak 行动正确写入 output.json
- [ ] 意识流 tick 固定 30 分钟一次（日志确认间隔）
- [ ] 用户发送消息后立即回复（不经过 tick 调度，走 SSE/judge 路径）
- [ ] **ActivitySelector 不再被调用**（日志确认）
- [ ] **ExpressionGate 不再被调用**（日志确认）
- [ ] **pending_expression.evaluate_and_generate 不再被调用**
- [ ] **四种 tick type 不再存在**（仅一种 `consciousness`）

### 运行观察期

- [ ] AI 有时选择 speak，有时选择 rest（不是总做同一个行动）
- [ ] speak 的内容不机械重复
- [ ] think 让 AI 产生了跨 tick 的连续性（`last_thought` 不是空的）
- [ ] recall 从真实的记忆中提取了内容
