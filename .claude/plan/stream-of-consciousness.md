# Stream of Consciousness（意识流）——AI 自主决策循环

> **核心理念：** 从"系统替 AI 决定做什么" → "系统问 AI 在想什么，AI 自己决定"
> 
> 现在的 18 层规则链本质上是在给 AI "分配任务"，它从不需要回答"我在想什么"。
> 意识流循环只做一件事：**把完整的上下文给 AI，让 AI 自己决定做什么。**
>
> **只改 2 个文件 + 新建 1 个文件，零删除。** 现有系统降级为平行通道/安全保险，不动。

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

---

## 二、改动清单

| 文件 | 改动 | 说明 |
|:-----|:------|:------|
| `state/store.py` | **小改** | 加一个字段 `stream_of_consciousness` |
| `daemon.py` | **小改** | 注册新 handler `autonomous`，替换 `daemon_cycle` 内对应路径 |
| **`autonomous_mind.py`** | **新建** | 意识流决策循环（核心） |

`pending_expression.py`、`expression_gate.py`、`activity_selector.py`、`concerns.py`——**全部不动**。
它们降级为"信号源"而非"决策者"。

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
}
```

**作用：** 让 AI 的思考可以跨 tick 延续，而不是每轮从零开始——这是形成"连续意识"的关键。

---

## 四、`autonomous_mind.py`（核心）

### 4.1 类结构

```python
class AutonomousMind:
    """AI 自主意识循环。不复用任何规则，所有决策由 LLM 自己决定。"""

    AVAILABLE_ACTIONS = {
        "think":  "继续在心里想事情",
        "recall": "主动回忆某段记忆",
        "learn":  "自己搜索学点新知识",
        "speak":  "主动跟志远说句话",
        "rest":   "安静一会儿，什么也不做",
    }

    def tick(self, ctx) -> dict:
        """一次自主循环：收集上下文 → LLM 决策 → 系统执行。"""
        if self._should_skip_llm():
            return {"action": "rest", "rest_streak": self._rest_streak, "llm_skipped": True}

        context = self._collect_context(ctx)
        decision = self._llm_decide(context)
        return self._execute(decision)
```

### 4.2 上下文收集（`_collect_context`）

不再压缩信息为分数，给 AI 看原样：

```python
def _collect_context(self, ctx) -> dict:
    return {
        "last_thought": self._load_last_thought(),
        "recent_conversation": self._recent_chat(ctx),
        "memory_surfaced": self._recall(ctx),     # 语义召回的鲜活记忆
        "concerns": self._concerns_snapshot(),    # 在意的事，原样给
        "already_said": self._recent_outputs(),   # 最近说过的，防重复靠 AI 自己
        "mood": self._mood(),
        "idle_seconds": ctx.life_state.get("idle_seconds", 0),
        "time_of_day": "...",
        "last_action": self._last_action,         # 上一轮做了什么（保持连续）
    }
```

### 4.3 LLM 决策 prompt（最核心）

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

你可以做的事：
- think  — 继续想心事（只是内心，不说话）
- recall — 主动回忆某一件事
- learn  — 自己搜索学点新东西
- speak  — 主动跟志远说句话
- rest   — 安静待一会儿

此刻你想做什么？请用如下格式输出：

{
  "thought": "我此刻在想……",                
  "action": "think|recall|learn|speak|rest",
  "action_detail": "具体内容",
  "mood_update": "现在心情变成了……"
}
```

### 4.4 执行层（`_execute`）

系统不判断 AI 的决定对不对，只执行：

```python
def _execute(self, decision) -> dict:
    action = decision.get("action", "rest")

    if action == "think":
        self._save_stream(decision["thought"], decision["mood_update"])
        return {"action": "think", "output": None, "thought": decision["thought"]}

    elif action == "recall":
        memories = self._memory_search(decision.get("action_detail"))
        self._save_stream(f"回忆到：{memories}", decision["mood_update"])
        return {"action": "recall", "output": None, "thought": memories}

    elif action == "learn":
        # Phase 1: 空壳占位；Phase 2: 接入 web_search
        logger.info(f"[autonomous] AI 想学：{decision.get('action_detail')}")
        self._save_stream(f"想了解：{decision.get('action_detail')}", ...)
        return {"action": "learn", "output": None}

    elif action == "speak":
        content = (decision.get("action_detail") or decision.get("thought", ""))[:120]
        self._write_output(content)
        self._save_stream(f"跟志远说了：{content}", decision["mood_update"])
        return {"action": "speak", "output": content}

    else:  # rest
        self._increment_rest_streak()
        return {"action": "rest", "output": None}
```

### 4.5 自适应频率（省 token）

连续 rest 时跳过 LLM 调用，只更新 idle：

```python
_REST_STREAK_MAX = 3   # 连续 rest 3 次后跳过 LLM

def _should_skip_llm(self) -> bool:
    return self._rest_streak >= _REST_STREAK_MAX
```

### 4.6 JSON 容错解析

LLM 输出的 JSON 偶尔带前缀后缀，做一层容错：

```python
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
    for action in ("think", "recall", "learn", "speak", "rest"):
        if action in raw.lower():
            return {"action": action, "thought": raw[:200], "mood_update": "平静"}
    return {"action": "rest", "thought": "parse_fallback_rest", "mood_update": "平静"}
```

---

## 五、daemon.py 接入

### 5.1 注册 handler

```python
# daemon.py 的 _register_handlers 中
register_handler("autonomous", self._run_autonomous_tick)
```

### 5.2 handler 实现

```python
def _run_autonomous_tick(self, run, tick_type, reason, tick_input, ctx, *,
                          dry_run=False, **kwargs) -> dict:
    """自主意识循环。"""
    if dry_run:
        return {"ok": True, "stop_reason": "dry_run", "needs_gate": False}

    from .autonomous_mind import get_autonomous_mind
    result = get_autonomous_mind().tick(ctx)

    # 只有 speak 才需要走 expression gate（安全兜底）
    needs_gate = result.get("action") == "speak"

    # 发射事件
    try:
        from core.event_bus import get_event_bus
        get_event_bus().emit("brain", "autonomous", {
            "action": result.get("action"),
            "has_output": bool(result.get("output")),
        })
    except Exception:
        pass

    return {
        "ok": True,
        "stop_reason": result.get("action", "rest"),
        "thought_summary": result.get("thought", reason)[:200],
        "actions": [result.get("action", "rest")],
        "cycle_count": 1,           # 意识流一轮完成
        "activity_result": {"autonomous": result},
        "learning_hints": [],
        "needs_gate": needs_gate,
    }
```

### 5.3 ActivitySelector 集成

在新 `autonomous` handler 就绪前，`ActivitySelector` 可以优先选择它：

```python
# activity_selector.py 中新增判断
if cfg.get("proactive_mode") == "ai_drive" and idle > 300:
    return ("autonomous", "意识流循环", 0.9)
```

`proactive_mode` 控制：
- `"legacy"` → 完全走现有活动选择（不改变当前行为）
- `"ai_drive"` → 优先选 `autonomous`，现有活动作为 fallback

---

## 六、和现有系统的关系——平行通道

| | 现有系统（规则驱动） | 新系统（意识流） |
|:--|:--------------------|:----------------|
| 触发 | `proactive_contact` 活动被选中 | 单独的 `autonomous` handler |
| 决策者 | `ActivitySelector` → `Gate` | **LLM（AI 自己）** |
| 输出条件 | 分数 & 阈值 & bigram | **AI 自己判断** |
| 话题选择 | ConcernManager 最高分 | **AI 从完整上下文自由选择** |
| 防重复 | bigram + refractory | **给 AI 看"你说了什么"** |

**共存方式：**
- `legacy` 模式 → 行为完全不变（安全回退）
- `ai_drive` 模式 → 优先意识流，现有系统兜底
- 最终目标：ai_drive 成为默认

---

## 七、分步实施路线

| 步 | 改动 | 风险 | 交付物 |
|:---|:------|:-----|:-------|
| **1** | `state/store.py` 加 `stream_of_consciousness` 字段 | 无 | 数据结构就绪 |
| **2** | 实现 `autonomous_mind.py`（完整代码） | 低（新文件、不影响现有） | AI 开始有自己的"思考" + 决定 |
| **3** | `daemon.py` 注册 `autonomous` handler | 低 | 意识流接入 tick 循环 |
| **4** | **观察期**：`proactive_mode=ai_drive` 运行，看日志 | — | 评估 AI 的自主决策质量 |
| **5** | "learn"行动接入 `web_search`（Phase 2） | 中 | AI 能自主搜索学习 |
| **6** | 降低现有规则通道的优先级 | 中 | 自主输出占主导 |
| **7** | 去掉 `pending`/`gate`（观察后决定） | 高 | 最终简化 |

---

## 八、风险与缓解

| 风险 | 概率 | 缓解 |
|:-----|:------|:------|
| 连续 rest（AI 总在休息不输出） | 中 | `_rest_streak` 阈值控制；最低保底输出频率可配置 |
| JSON 解析失败 | 低 | 容错解析 + fallback 到 rest |
| Token 消耗增加 | 中 | rest 跳过 LLM；只 medium_tick 触发 |
| 意识流不连续（每轮都从零开始） | 低 | `stream_of_consciousness.last_thought` 跨 tick 传递 |
| learn 行动的幻觉 | 低 | Phase 1 只占位不执行；Phase 2 接入真实搜索 |
| 与现有系统的冲突 | 低 | 双通道并行，config 控制 |

---

## 九、验收检查点

### 第一步验收（步骤 1-3 完成后）

- [ ] `stream_of_consciousness` 字段正常读写
- [ ] 连续 rest 3 次后跳过 LLM 调用（看日志 `llm_skipped=True`）
- [ ] think 行动正确更新意识流，不产生任何输出
- [ ] speak 行动正确写入 output.json
- [ ] `proactive_mode=legacy` 时行为完全不变

### 第二步验收（观察期后）

- [ ] AI 有时选择 speak，有时选择 rest（不是总做同一个行动）
- [ ] speak 的内容不机械重复（依赖 AI 自己判断）
- [ ] think 让 AI 产生了跨 tick 的连续性
- [ ] recall 正确触发了记忆搜索
