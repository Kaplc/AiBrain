# mem0 独立服务 —— 与 Flask 主进程解耦

## 一、项目目标

- **项目名称**：mem0 独立服务化（mem0 Standalone Service）
- **一句话描述**：将 mem0 客户端从主 Flask 进程中分离，独立为一个 Flask 服务进程，避免主进程重启时重新加载 BGE-M3 语义模型（~40s）。
- **核心目标**：
  1. mem0 独立进程运行，加载 BGE-M3 + Qdrant 连接，不随主 Flask 重启
  2. 主 Flask 通过 HTTP API 调用 mem0 服务
  3. mem0 服务启动后常驻，主 Flask 多次重启不受影响
  4. 与现有代码完全兼容，`get_mem0_client()` 改为 HTTP 调用，调用方无感知
- **不做的事**：
  - 不改变 Qdrant 的部署方式（Qdrant 已经是独立进程）
  - 不改变 mem0 的数据存储结构和配置格式（`mem0.json` 沿用）
  - 不涉及前端改动

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| 重启慢 | 每次改 py 代码重启 Flask，BGE-M3 重载 ~40s | 开发效率低 |
| mem0 耦合 | mem0 client 是 Flask 进程内单例，全量加载 | 模型占用内存不释放 |
| 无法独立部署 | 无法单独重启记忆服务而不影响聊天 | 缺乏灵活性 |

### 2.2 目标场景

```
场景1：修改聊天逻辑后重启 Flask
  → 主 Flask 重启（~2s）
  → mem0 服务不受影响，继续提供服务
  → 不需要等 BGE-M3 加载

场景2：独立升级 mem0 服务
  → 重启 mem0 服务（~40s）
  → 主 Flask 不受影响，只是暂时无法存取记忆
```

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| mem0 服务进程 | 独立运行的 Flask 服务，加载 BGE-M3 + 连接 Qdrant | **P0** | 主进程解耦 |
| 存储 API | `POST /memory/add` — 存一条记忆 | **P0** | 替代 `mem0.add()` |
| 搜索 API | `POST /memory/search` — 搜索记忆 | **P0** | 替代 `mem0.search()` |
| 获取 API | `GET /memory/get/<id>` — 获取单条 | **P1** | 替代 `mem0.get()` |
| 删除 API | `DELETE /memory/delete/<id>` — 删除 | **P1** | 替代 `mem0.delete()` |
| 列表 API | `POST /memory/list` — 列出记忆 | **P1** | 替代 `mem0.get_all()` |
| 更新 API | `POST /memory/update/<id>` — 更新 | **P1** | 替代 `mem0.update()` |
| 计数 API | `GET /memory/count` — 记忆数量 | **P2** | 替代 `get_memory_count()` |
| 客户端兼容层 | 现有 `mem0_adapter.py` 改为 HTTP 调用，外部无感知 | **P0** | 零改动 |

---

## 四、非功能需求

- **性能**：HTTP 调用延迟 < 5ms（本地 localhost）
- **兼容性**：所有现有 `from modules.brain.mem0_adapter import get_mem0_client` 调用不变
- **端口**：mem0 服务监听动态端口（从 `.port_config` 第二端口，当前 19399 被 Qdrant 占用，可用 19400）
- **服务发现**：mem0 端口写入 `.port_config` 或环境变量

---

## 五、系统架构

### 5.1 架构图

```
┌──────────────────┐         HTTP          ┌─────────────────────┐
│  主 Flask 进程    │ ◄──────────────────► │  mem0 服务进程       │
│  (app.py)         │    POST /memory/add   │  (mem0_server.py)   │
│                   │    POST /memory/search│                     │
│  - chat           │    ...                │  - BGE-M3 模型      │
│  - routes         │                       │  - mem0 client      │
│  - pipeline       │                       │  - Qdrant 连接      │
│  - workmemory     │                       │                     │
│  - 不加载 BGE-M3  │                       │  - 常驻内存          │
└──────────────────┘                       └──────────┬──────────┘
                                                      │ gRPC/HTTP
                                                      ▼
                                               ┌──────────────┐
                                               │   Qdrant      │
                                               │   (独立进程)   │
                                               └──────────────┘
```

### 5.2 端口规划

| 服务 | 当前端口 | 说明 |
|------|---------|------|
| 主 Flask | 19398 | 不变 |
| Qdrant | 19399 | 不变，独立进程 |
| mem0 服务 | 19400 | 新增，写入 `.port_config` 第四位 |

### 5.3 目录结构

```
backend/
├── mem0_server/               # [新增] mem0 独立服务
│   ├── __init__.py
│   ├── server.py              # Flask 服务入口
│   ├── routes.py              # API 路由
│   └── client_adapter.py      # HTTP 客户端（适配原有接口）
│
├── modules/brain/
│   └── mem0_adapter.py        # [改] 改为调 client_adapter，不直接创建 mem0
│
├── launcher/
│   └── start.py               # [改] 启动时拉起 mem0 服务进程
│
└── app.py                     # [改] 去掉 BGE-M3 加载（移入 mem0_server）
```

### 5.4 启动流程

```
启动顺序：
  1. Qdrant（已有）
  2. mem0 服务（新增）→ 加载 BGE-M3 → 连接 Qdrant
  3. 主 Flask（连接 mem0 服务，不加载 BGE-M3）

重启流程（仅主 Flask）：
  → 主 Flask 重启（~2s）
  → mem0 服务不受影响
  → BGE-M3 不需要重载
```

### 5.5 关键设计决策

1. **HTTP 通信**：最简单，同一台机器 localhost 延迟 ~1ms，可接受
2. **客户端适配器**：`mem0_adapter.py` 内部改用 HTTP 调用，保持 `get_mem0_client()` 返回的对象接口不变（`add/search/delete/update/get_all`）
3. **mem0 服务无状态**：服务只持有 mem0 client 单例，不存业务数据，可以随时重启
4. **优雅降级**：主 Flask 调 mem0 服务失败时，降级返回空结果，不影响主流程

---

## 六、数据结构

### 6.1 API 请求/响应

```python
# 存储
POST /memory/add
Request:  {"text": "...", "user_id": "...", "infer": true, "metadata": {...}}
Response: {"results": [{"id": "...", "memory": "...", "event": "ADD"}], ...}

# 搜索
POST /memory/search
Request:  {"query": "...", "filters": {...}, "top_k": 75, "threshold": 0.55}
Response: {"results": [{"id": "...", "memory": "...", "score": 0.85}], ...}

# 列出
POST /memory/list
Request:  {"filters": {...}, "top_k": 10000}
Response: {"results": [{"id": "...", "memory": "...", "created_at": "..."}], ...}

# 删除
POST /memory/delete
Request:  {"id": "..."}
Response: {"ok": true}

# 获取
POST /memory/get
Request:  {"id": "..."}
Response: {"id": "...", "memory": "...", ...}
```

### 6.2 客户端适配器（mem0_adapter.py 改造）

```python
# 改造前：直接创建 mem0 client
def get_mem0_client():
    return Memory.from_config(config)

# 改造后：返回 HTTP 客户端代理
def get_mem0_client():
    return Mem0HttpClient(host="127.0.0.1", port=19400)

# Mem0HttpClient 实现 add/search/delete/update/get_all/get
# 接口与 mem0 client 一致，调用方无感知
```

---

## 七、流程设计

### 1. 主 Flask 启动（改造后）

```
create_app()
  → ...（不加载 BGE-M3，不创建 mem0 client）
  → 注册路由
  → 首次请求时懒初始化 mem0 服务连接
  → 预热记忆数量缓存（通过 HTTP 调 mem0 服务）
```

### 2. 写入记忆

```
store_memory(text)
  → get_mem0_client() → Mem0HttpClient
  → POST /memory/add  → mem0 服务 → mem0.add() → Qdrant
  ← 返回结果
  → 后续：实体提取、图链接、事件提取（这些仍在主 Flask 进程）
```

### 3. 搜索记忆

```
search_memory(query)
  → get_mem0_client() → Mem0HttpClient
  → POST /memory/search → mem0 服务 → mem0.search() → Qdrant
  ← 返回结果
  → 后续：事件召回、图增强、时间衰减（这些仍在主 Flask 进程）
```

### 4. mem0 服务优雅降级

```
主 Flask 调 mem0 服务超时或失败
  → 记录 WARNING 日志
  → 返回空结果（搜索返回 []，存储返回空）
  → 不阻塞主流程
```

---

## 八、API 设计

### 8.1 mem0 服务 API

| 方法 | 路径 | 说明 | 对应 mem0 方法 |
|------|------|------|---------------|
| POST | `/memory/add` | 存储记忆 | `client.add()` |
| POST | `/memory/search` | 搜索记忆 | `client.search()` |
| POST | `/memory/list` | 列出记忆 | `client.get_all()` |
| POST | `/memory/get` | 获取单条 | `client.get()` |
| POST | `/memory/delete` | 删除记忆 | `client.delete()` |
| GET | `/health` | 健康检查 | — |

所有接口的请求/响应格式与 mem0 原始 SDK 保持一致。

### 8.2 客户端接口（不变）

现有调用方完全无感知：

```python
# 改造前后代码完全一样
from modules.brain.mem0_adapter import get_mem0_client
client = get_mem0_client()
result = client.add(text, user_id="default", infer=True)
results = client.search(query, filters={"user_id": "default"}, top_k=75)
```

---

## 九、验收标准

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|---------|
| A1 | mem0 服务独立启动 | 启动 `mem0_server.py` | 端口 19400 监听，返回 200 |
| A2 | 存储记忆 | POST `/memory/add` | 返回正常结果 |
| A3 | 搜索记忆 | POST `/memory/search` | 返回正常结果 |
| A4 | 主 Flask 不加载 BGE-M3 | 重启主 Flask | 日志无 "Model loaded" |
| A5 | 主 Flask 启动快 | 重启主 Flask | 2s 内就绪 |
| A6 | 兼容层正常工作 | 调用 `get_mem0_client().add()` | 结果与改造前一致 |
| A7 | 优雅降级 | 关闭 mem0 服务 → 搜索 | 主流程不崩溃 |
| A8 | 独立重启 | 重启 mem0 服务 → 再次搜索 | 主 Flask 不需重启 |

---

## 十、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 预估代码量 | 所属模块 |
|---------|----------|------|--------|-----------|---------|
| T001 | mem0 服务 Flask 入口（server.py + routes.py + 健康检查） | 无 | M | ~80 行 | mem0_server/ |
| T002 | HTTP 客户端适配器（Mem0HttpClient 实现 add/search/delete/get_all/get） | T001 | M | ~100 行 | mem0_server/client_adapter.py |
| T003 | mem0_adapter.py 改造（改为返回 Mem0HttpClient） | T002 | S | ~20 行 | modules/brain/mem0_adapter.py |
| T004 | 主 Flask app.py 去掉 BGE-M3 加载 | T003 | S | ~10 行 | app.py |
| T005 | launcher/start.py 集成（启动时拉起 mem0 服务） | T001 | M | ~30 行 | launcher/start.py |
| T006 | `.port_config` 更新 + 端口分配 | T001 | S | ~5 行 | .port_config |
| T007 | E2E 测试（存+搜+独立重启） | T001-T006 | M | ~60 行 | tests/ |

**预估工作量**：约 4-6 小时，~300 行代码

**并行分组**：
- 组1：T001 + T006（mem0 服务 + 端口）
- 组2：T002 + T003（客户端适配器 + adapter 改造）
- 组3：T004 + T005（主 Flask 清理 + launcher 集成）
- 组4：T007（测试）

---

**文档信息**
- 生成日期: 2026-06-07
- 文档版本: v1.0
