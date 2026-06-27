# 外部刺激捕获与自我状态更新模块（优化版）

在 main_brain 中新增一个轻量模块，将外部事件（聊天、HTTP、MCP tool）转化为 `BrainEvent` 送入现有的 `Orchestrator` 事件回路，合并后触发 `BrainSession.run_stimulus()` 更新 AI 的自我状态。

---

## 核心目标

1. 所有外部事件通过 `BrainEvent` 统一接入 `Orchestrator` 事件回路
2. 密集事件通过 tick_buffer + cooldown 节流，不每条单独触发 LLM
3. 在 `BrainSession` 中新增 `run_stimulus()` 方法，复用 BrainJudge + controller 但跳过 chat 专属副作用（mark_user_contact、recent_conversation 注入等）
4. 新状态（mood/energy/focus/drives/recent_thoughts）落盘到现有 life 节点

**不做的事**：不改 chat loop 回复流程、不新增 judge 类型、不存刺激到长时记忆、不建平行队列。

---

## 问题现状

自我状态只在 brain loop tick 或每日反思时更新，外部事件不参与，导致 mood/energy 滞后于真实活动。encoder 存记忆时读到的 life_state 可能过时。

---

## 优化依据

项目已存在完整的统一事件基础设施，无需另建平行系统：

| 计划原方案（已废弃） | 已有替代 |
|---|---|
| `StimulusCollector._queue` 独立队列 | `Orchestrator.process_event()` — 完整事件管线 |
| `SourceRegistry` 自定义注册表 | `Router.register(source, type, handler)` — 全局路由 |
| `StimulusItem` / `SourceInfo` 新数据结构 | `BrainEvent` — 已统一包装所有刺激 |
| `controller.run()` 直接调用（跳过生命周期） | `BrainSession.run_reactive()` — 含完整上下文注入 |
| 三个 source 文件重复模式 | 一个通用 collect() 函数 + Router 注册 |

---

## 架构设计

**核心模式**：一个统一的 `collect_stimulus()` 入口函数，将外部事件包装为 `BrainEvent` 送入 Orchestrator。

```python
from main_brain.stimulus import collect_stimulus
collect_stimulus("chat.summary", "用户询问了关于X的问题")
```

**新增刺激源只需**：在其他代码中调 `collect_stimulus(type, summary)` 即可，不改 stimulus 核心，不新增文件。

### 目录结构

```
backend/main_brain/
└── stimulus/
    ├── __init__.py              ← 导出 collect_stimulus() + init_stimulus()
    └── handler.py               ← Router handler + 合并节流逻辑
```

### 数据流

```
各处事件 (chat / HTTP / MCP)
    │  collect_stimulus(source_type, summary, metadata=None)
    ▼
handler.py: _on_stimulus()          ← 通过 Router("stimulus", type) 路由
    │  ① 总开关检查 → 关则 return
    │  ② 线程安全加锁 (threading.Lock)
    │  ③ 合并节流检查：
    │     - 距上次触发 < cooldown: 入 tick_buffer，等下次
    │     - buffer ≥ max_batch: 调 _flush()
    │     - 否则跳过
    ▼
_flush():
    │  ① 构造 stimulus_context dict
    │  ② BrainSession.run_stimulus()  ← 新入口，非 chat 路径
    │  ③ 清空 buffer
    │  ④ 更新 _last_trigger_at
    ▼
BrainSession.run_stimulus(stimulus_context)
    │  轻量状态更新路径（单独方法，不混入 run_reactive）
    │  - 读取 LifeState
    │  - 跳过: mark_user_contact / set_loop_status("chatting")
    │  - 跳过: recent_conversation 注入
    │  - 跳过: max_cycles（固定 1 轮）
    │  - 注入: procedural memory
    │  - BrainJudge 决策（idle prompt, max_cycles=1）
    │  - adapter 执行 (update_state → mood/energy/focus)
    │  - 沉淀 learning_hints
    │  - 更新 life node
    ▼
LifeState 落盘 (internal_state.json['life'])
```

### 数据结构

不新增数据类，全部复用现有。`stimulus_context` 约定为一个 dict：

```python
# stimulus_context 约定格式
{
    "type": str,          # 刺激源类型: "chat" / "http_save" / "mcp_tool"
    "summary": str,       # 事件摘要（≤200 字符）
    "source": str,        # 来源（同 type，保持一致性）
    "metadata": dict,     # 可选：附加字段如 {url, tool_name, ...}
}
```

复用已有数据类：
- `BrainEvent` — 事件载体（添加 `EVENT_SOURCE_STIMULUS = "stimulus"` 到 contracts.py）
- `BrainRunContext` — 运行上下文
- `BrainJudgeDecision` — LLM 决策输出
- `BrainCycle` / `BrainRun` — 循环记录

### 合并节流机制

直接在 handler 内做轻量状态检查：

- `stimulus_cooldown_seconds`（默认 30s）：距上次触发 < cooldown 时，stimulus 入 tick_buffer 暂存
- `stimulus_max_batch`（默认 5）：buffer 积压 ≥ 此值时强制触发
- `_buffer: list[dict]` + `_buffer_lock = threading.Lock()` 保证线程安全
- 每次 `_flush()` 完成后清空 buffer
- LifeLoop 的 medium_tick 通过 `handler.flush_pending_stimuli()` 显式调用做兜底触发

### 配置项（默认关）

```python
# 加到 DEFAULT_BRAIN
"external_stimulus_enabled": False,      # 总开关（运行时动态读取）
"stimulus_cooldown_seconds": 30,         # 合并窗口（秒）
"stimulus_max_batch": 5,                 # 强制触发阈值
```

### 异常处理

- `main_brain` / `Orchestrator` 不可用：静默降级，不抛到上层
- `BrainSession.run_stimulus()` 抛异常：buffer **不清空**，下次重试
- buffer 超上限（>50）：FIFO 丢弃最旧的，日志记录 `[stimulus] dropped N old events (buffer full)`

---

## 开发任务

| 任务 | 内容 | 依赖 | 预估 |
|---|---|---|---|
| T001 | contracts.py 加 `EVENT_SOURCE_STIMULUS` 常量 | 无 | S |
| T002 | session.py 加 `run_stimulus()` 方法（轻量版，跳过 chat 副作用） | T001 | S |
| T003 | stimulus 包结构: `__init__.py` + `handler.py`（collect_stimulus / _on_stimulus / _flush / 线程安全 buffer/ 异常处理） + Router 注册 | T002 | S |
| T004 | daemon.py medium_tick 加入 `flush_pending_stimuli()` 调用 | T003 | S |
| T005 | 注入点: chat loop / HTTP routes / MCP tools 调 collect_stimulus() | T003 | S |
| T006 | E2E 验证 | T005 | M |

依赖链：T001 → T002 → T003 → T004, T003 → T005 → T006

---

## 验收要点

1. 发消息 → 日志出现 `[stimulus] collected chat` + `[stimulus] triggered BrainSession`
2. 触发后 life 节点 mood/focus/recent_thoughts 有更新
3. 5 秒内连续 3 条消息 → 仅 1 次 LLM 调用（合并节流）
4. `external_stimulus_enabled=false` → collect_stimulus() 直接 return
5. HTTP 存记忆 → `[stimulus] collected http_save`
6. `run_stimulus()` 抛异常 → 主流程不中断，buffer 不清空
7. medium_tick 扫描 buffer → 积压 stimulus 被触发 → 日志出现 `[stimulus] flushed by medium_tick`
8. FIFO 丢弃触发 → 日志记录 `[stimulus] dropped N old events (buffer full)`

### 交付物

新增：
- `stimulus/__init__.py`
- `stimulus/handler.py`

修改：
- `main_brain/contracts.py`（+ `EVENT_SOURCE_STIMULUS` 常量）
- `main_brain/session.py`（+ `run_stimulus()` 方法）
- `main_brain/__init__.py`（导入 init_stimulus）
- `main_brain/config.py`（+3 行配置）
- `main_brain/daemon.py`（medium_tick 加 `flush_pending_stimuli()`）

注入点（各加一行 collect_stimulus）：
- `modules/chat/loop.py`（或 chat_routes 中）
- `routes/memory_routes.py`（/memory/store + /memory/mcp/store）
- `brain_mcp/tools.py`（store_memory 中）
