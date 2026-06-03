# 实体网络重建 UI 集成

## 一、项目目标

- **项目名称**：实体网络重建 UI 集成
- **一句话描述**：将 `backend/modules/brain/rebuild_graph.py` 整合到记忆页面的「实体 Tab」，通过「重建实体网络」按钮触发，支持进度展示
- **核心目标**：
  1. 在 EntityTab 工具栏新增「重建实体网络」按钮
  2. 后端 Flask 进程内启动独立线程执行重建，不阻塞 API
  3. 进度保存到内存 state，前端每 2s 轮询拉取最新状态
  4. 完成后自动刷新实体统计
- **不做的事**：
  - 不修改 `rebuild_graph.py` 核心业务逻辑（已加上空记忆重试）
  - 不做任务队列/调度（单实例单任务）
  - 不做实时日志流推送（不持久化 progress.json）
  - 不做崩溃恢复（Flask 重启后状态清空）

---

## 二、业务背景

- **问题现状**：
  - `rebuild_graph.py` 只能手动在终端跑，不友好
  - 跑的时候看不到进度，只能等结束后看 log
  - 跑期间不知道还剩多少
- **目标用户**：使用 AiBrain 桌面壳的开发者/重度用户
- **预期价值**：
  - 图形界面一键触发，无需打开终端
  - 实时看到进度（处理了多少/总共多少）
  - 完成后看到最终统计

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 重建按钮 | 作为用户，我在 Entity Tab 看到「重建实体网络」按钮 | P0 | 工具栏右侧 |
| 异步执行 | 作为用户，我点击按钮后页面不卡死 | P0 | 后端独立线程跑重建 |
| 进度展示 | 作为用户，我能看到百分比 + 当前处理数 | P0 | 轮询接口读 state |
| 状态查询 | 作为用户，我能查看当前是否在跑 | P0 | GET 接口读 state |
| 自动刷新 | 作为系统，重建完成后自动加载新统计 | P0 | 完成后前端再请求 |
| 取消按钮 | 作为用户，我能中途停止 | P1 | POST 接口设 stop_flag |
| 错误展示 | 作为用户，我能看到错误信息 | P1 | 后端 logger 末尾 100 行 |
| 切换 Tab 恢复进度 | 作为用户，我从其他 Tab 切回 Entity Tab 时，进度条自动恢复 | P0 | onMounted 重新拉取后台 state |
| 跨 Tab 状态可见 | 作为用户，我在其他 Tab 也能看到「正在重建」的提示 | P2 | NavSidebar 状态点 |

---

## 四、非功能需求

- **性能**：进度查询接口响应 < 200ms
- **并发**：同时只能跑一个重建任务（第二个会被拒绝）
- **可观测**：进度保存在内存中（RebuildService.state），不持久化
- **无特殊要求**：无安全要求（本地工具）

---

## 五、系统架构

```
┌──────────────────────────────────────────────┐
│         EntityPanel.vue (前端)               │
│  [重建实体网络] [刷新]  ← 工具栏新增按钮     │
│       ↓ 点击                                  │
│  POST /memory/graph/rebuild                  │
│       ↓                                       │
│  显示进度条 (轮询 GET /memory/graph/rebuild) │
└─────────────────┬────────────────────────────┘
                  │ HTTP
┌─────────────────▼────────────────────────────┐
│        memory_routes.py (Flask 进程内)       │
│  POST /memory/graph/rebuild 启动线程         │
│  GET  /memory/graph/rebuild 读内存 state     │
│  POST /memory/graph/rebuild/cancel 设标志位  │
│  ┌────────────────────────────────────────┐  │
│  │ RebuildService (单例)                   │  │
│  │ ├── state: dict (内存，进度信息)        │  │
│  │ ├── thread: Thread (后台跑重建)        │  │
│  │ └── stop_flag: bool (取消标志)          │  │
│  └────────────────────────────────────────┘  │
│       ↑                                       │
│  rebuild_thread 直接调用 rebuild_graph 模块  │
│  日志复用后端 logger 写日志                   │
└──────────────────────────────────────────────┘
```

**目录结构**：
```
backend/
├── routes/
│   └── memory_routes.py     # 修改：新增 3 个 API
├── core/
│   └── rebuild_service.py   # 新增：RebuildService 单例（线程 + 内存 state）
└── modules/brain/
    ├── graph.py              # 已有，不改
    └── rebuild_graph.py      # 移动：scripts/ → backend/modules/brain/
                              # 改造：从 main 函数改为可被 import 的模块
                              # 不再写 progress.json（改为内存 state）

web/src/views/MemoryView/EntityTab/
├── EntityPanel.vue           # 修改：新增按钮 + 进度条
├── EntityTab.ts              # 修改：增加 rebuild 相关 state
└── EntityMgr.ts              # 修改：调用 API
```

**脚本移动说明**：
- 原因：`rebuild_graph.py` 依赖 backend 模块（`from modules.brain.llm import extract_entities_llm`）
- 目标位置：`backend/modules/brain/rebuild_graph.py`（与依赖的 brain 模块同目录）
- 调整项：
  - `sys.path.insert` 路径调整（已在 brain 模块同目录，可直接 import）
  - 改造：从 `if __name__ == "__main__"` 入口改为 `def rebuild(state_dict, stop_flag):` 函数
  - 函数接收 `state`（dict）和 `stop_flag`（bool），用于实时更新和取消
  - 删掉原 `clear_graph` + `rebuild()` 的 main 流程包装

**日志统一说明**：
- 现状：脚本独立配置 `FileHandler('rebuild_graph.log')` + `StreamHandler`
- 目标：复用 `backend/core/logger.py` 的日志系统
- 改造点：
  1. 删除脚本内的 `logging.basicConfig`
  2. 改用 `from core.logger import get_logger` 或类似统一接口
  3. 日志输出与后端一致（按角色分文件，归档保留 3 个）
  4. 角色名：`rebuild` 或 `brain`（视后端 logger 配置而定）
  5. `rebuild_graph.log` 文件可以删除（合并到后端日志体系）
- 好处：
  - 不用单独管理脚本日志归档
  - 调试时一处查看所有后端日志
  - 日志格式与时间戳与后端一致

---

## 六、数据结构

### RebuildService.state（内存变量）

```python
state: dict = {
    "status": "running" | "completed" | "failed" | "idle",
    "started_at": "2026-06-02T10:00:00",
    "finished_at": None,
    "total": 374,
    "processed": 100,
    "success": 95,
    "empty": 3,
    "failed": 2,
    "retry_success": 0,
    "current_phase": "first_pass" | "retry" | "finished",
    "workers": 5,
    "llm_calls": 245,
    "llm_calls_success": 240,
    "llm_calls_failed": 5,
}
```

**注意**：不持久化，Flask 重启后状态清空。

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 状态：running/completed/failed/idle |
| started_at | string | 启动时间（ISO 格式） |
| finished_at | string\|null | 完成时间 |
| total | int | 总记忆数 |
| processed | int | 已处理数（实时更新） |
| success | int | 成功数 |
| empty | int | 空实体数 |
| failed | int | 失败数 |
| retry_success | int | 重试成功数 |
| current_phase | string | 当前阶段：first_pass/retry/finished |
| workers | int | 线程数（运行时展示用） |
| llm_calls | int | LLM 调用总次数（实时更新） |
| llm_calls_success | int | LLM 调用成功次数 |
| llm_calls_failed | int | LLM 调用失败次数 |
| elapsed_seconds | int | 已运行秒数（前端计算：now - started_at） |

---

## 七、流程设计

### 7.1 启动重建任务

```
用户点击「重建实体网络」按钮
        ↓
前端 POST /memory/graph/rebuild
        ↓
后端检查 RebuildService 是否有任务在跑
    ├── 是 → 返回 409 "已有任务在跑"
    └── 否 → 启动新线程
              ├── 初始化内存 state (status=running, total=N)
              └── thread.start() → 执行 rebuild_graph.rebuild()
        ↓
返回 200 {started: true}
        ↓
前端启动轮询（每 2s GET 一次）
```

### 7.2 重建线程流程

```
RebuildService.start() 被调用
        ↓
在内存初始化 state (status=running, total=N)
        ↓
Thread 启动 → 调用 rebuild_graph.rebuild(state, stop_flag)
        ↓
读取 Qdrant → 获取所有记忆
        ↓
state["total"] = N
        ↓
第一轮（多线程提取实体）
    ├── 每完成一条 → state["processed"] += 1
    ├── 每调用 LLM 一次 → state["llm_calls"] += 1
    ├── 抽到实体 → state["success"] += 1
    ├── 抽到空 → state["empty"] += 1
    └── LLM 失败 → state["llm_calls_failed"] += 1
    ├── 检查 stop_flag，若 True → 退出
    └── 写日志到后端 logger
        ↓
第二轮（重试空记忆）
    ├── 每完成一条 → state["processed"] += 1
    ├── 重试成功 → state["retry_success"] += 1
    └── 检查 stop_flag
        ↓
state["status"] = "completed"
state["finished_at"] = now()
```

### 7.3 前端轮询

```
EntityTab onMounted:
    ↓
GET /memory/graph/rebuild
    ↓
读 RebuildService.state
    ↓
if status === "running":
    启动 setInterval(2000ms) 轮询
elif status === "completed":
    加载新统计（最新数据）
elif status === "idle":
    显示「点击按钮开始」
```

### 7.4 取消流程

```
用户点击「取消」按钮
        ↓
POST /memory/graph/rebuild/cancel
        ↓
RebuildService.stop() 被调用
        ↓
设置 stop_flag = True
        ↓
rebuild 线程在下一次循环检查 stop_flag 时退出
        ↓
state["status"] = "idle"
state["finished_at"] = now()
```

---

## 八、API 设计

### 8.1 启动重建

**POST /memory/graph/rebuild**

```
Request: 无
Response:
{
  "success": true,
  "started": true
}

错误：
409: { "error": "已有任务在跑" }
500: { "error": "启动失败: xxx" }
```

### 8.2 查询进度

**GET /memory/graph/rebuild**

```
Response:
{
  "status": "running" | "completed" | "failed" | "idle",
  "started_at": "2026-06-02T10:00:00",
  "finished_at": null,
  "total": 374,
  "processed": 100,
  "success": 95,
  "empty": 3,
  "failed": 2,
  "retry_success": 0,
  "current_phase": "first_pass",
  "progress_pct": 26,
  "workers": 5,
  "llm_calls": 245,
  "llm_calls_success": 240,
  "llm_calls_failed": 5,
  "elapsed_seconds": 120
}
```

### 8.3 取消重建

**POST /memory/graph/rebuild/cancel**

```
Request: 无
Response:
{
  "success": true,
  "message": "已设置停止标志，任务将终止"
}

错误：
409: { "error": "没有任务在跑" }
```

---

## 九、验收标准

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|----------|
| A1 | 按钮显示 | 进入记忆页面 → 实体 Tab | 工具栏显示「重建实体网络」按钮 |
| A2 | 点击触发 | 点击按钮 | 显示进度条，0% → 100% |
| A3 | 进度实时更新 | 观察进度条 | 每 2s 更新一次，processed 字段递增 |
| A4 | 异步不阻塞 | 点击后操作其他 Tab | 页面正常响应，不卡顿 |
| A5 | 完成后自动刷新 | 等待完成 | 自动重新加载统计，显示新数据 |
| A6 | 拒绝并发 | 重建进行中再次点击 | 提示「已有任务在跑」 |
| A7 | 取消功能 | 重建中点击取消 | 进度停止，状态变 idle |
| A8 | 错误展示 | 重建过程中 LLM 报错 | 界面显示「失败」状态，可看 logger 日志末尾 100 行 |
| A9 | 空记忆重试 | 跑完后看 log | 空记忆被重试一次，记录 retry_success |
| A10 | 切换 Tab 恢复进度 | 启动重建后切换到 Graph Tab，再切回 Entity Tab | 进度条自动恢复，轮询重新启动 |
| A11 | 线程数展示 | 重建时观察 UI | 显示「线程数: 5」 |
| A12 | LLM 调用次数展示 | 重建时观察 UI | 显示「模型调用: 245 次（成功 240 / 失败 5）」，实时递增 |
| A13 | LLM 成功率 | 跑完后看统计 | 显示成功率百分比 |
| A14 | Flask 重启状态清空 | 跑期间重启 Flask | state 重置为 idle（不持久化） |

---

## 十、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 所属模块 |
|---------|---------|------|--------|---------|
| T001 | 移动 rebuild_graph.py 到 backend/modules/brain/，改造成可 import 的模块 + 接入后端 logger | 无 | S | backend/modules/brain |
| T002 | 新增 core/rebuild_service.py：RebuildService 单例（线程 + 内存 state） | T001 | M | backend/core |
| T003 | 后端：3 个 API 端点（启动/查询/取消） | T002 | M | backend/routes |
| T003b | 后端：实现错误日志接口（GET /memory/graph/rebuild/log 返回末尾 100 行） | T002 | S | backend/routes |
| T004 | 前端 EntityMgr.ts 增加调用方法 | T003 | S | web/EntityTab |
| T005 | 前端 EntityPanel.vue 加按钮 + 进度条 | T004 | M | web/EntityTab |
| T006 | 完成后自动刷新统计 | T005 | S | web/EntityTab |
| T007 | 前端：取消按钮 + 错误展示 | T005, T003b | S | web/EntityTab |
| T008 | 切换 Tab 自动拉取后台状态 + 恢复轮询 | T005 | S | web/EntityTab |

**任务依赖图**：
```
T001 (移动 + 改模块) ─┐
                      ├─→ T002 (RebuildService) ─→ T003 (API 启动/查询/取消)
                      │                            └→ T003b (API 日志查询)
                      │                                │
                      └─→ (无其他依赖)                  ↓
                                                   T004 (前端 Mgr)
                                                      ↓
                                                   T005 (UI 按钮)
                                                      ├─→ T006 (自动刷新)
                                                      ├─→ T007 (取消 + 错误)
                                                      └─→ T008 (Tab 切换恢复)
```

**预估工作量**：约 6-8 小时。

---

**文档信息**
- 生成工具: skl-project-planner
- 生成日期: 2026-06-02
- 文档版本: v1.0