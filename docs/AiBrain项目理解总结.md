# AiBrain 项目理解总结

> 生成时间：2026-06-04

## 1. 项目定位

AiBrain 当前仓库也保留了早期 `MemoryExtra` 命名痕迹。整体是一个本地运行的记忆/知识管理系统，核心能力包括：

- 基于 `mem0` + Qdrant 的长期记忆存储、搜索、更新、删除。
- 基于本地 `BAAI/bge-m3` embedding 模型的语义检索。
- 记忆实体抽取、实体关系图谱、事件时间线与图谱重建。
- Wiki/RAG 索引与搜索，使用 LightRAG 相关数据目录。
- Vue 3 前端界面，Flask 后端统一托管 API 和构建后的前端页面。
- MCP 服务入口，向外暴露记忆存储和搜索能力。

这是一个偏“本地桌面应用 + 本地后端服务 + 本地向量库”的项目，而不是单纯 Web 项目。

## 2. 目录结构

关键目录和文件：

- `backend/`：Flask 后端主目录。
- `backend/app.py`：正式后端入口，注册所有页面/API 路由，并优先托管 `web/dist`。
- `backend/core/`：后端通用核心模块，包括日志、设置、模型加载、SQLite 统计数据库、图谱重建服务。
- `backend/routes/`：Flask API 路由模块，按页面/功能拆分。
- `backend/modules/`：后端业务模块，包含记忆、图谱、Wiki、系统信息等具体逻辑。
- `backend/launcher/`：启动器和进程管理脚本。
- `web/`：Vue 3 + Vite 前端项目。
- `web/src/views/`：前端主页面，包含 `OverviewView`、`MemoryView`、`StreamView`、`WikiView`、`LogsView`、`SettingsView`。
- `web/src/components/`：全局布局组件，如侧边栏、状态栏、控制台面板。
- `web/src/stores/`：Pinia 状态管理。
- `brain_mcp/`：AiBrain Memory MCP 服务，主要暴露 `store` 和 `search` 两个工具。
- `mcp_servers/`：额外 MCP 服务目录，包括 computer、console、eye、wiki。
- `models/bge-m3/`：本地 embedding 模型目录。
- `qdrant/`：本地 Qdrant 数据库相关目录。
- `rag/`：LightRAG/Wiki RAG 数据目录。
- `logs/`：项目运行日志目录。
- `tests/`：根目录 Playwright 与 Python 测试。
- `.port_config`：当前运行端口配置，访问和测试后端时应读取该文件。
- `AGENTS.md`：本地协作规则。

## 3. 启动链路

常用启动入口：

- `start.bat`
- `start.py`
- `launch.py`
- `backend/launcher/start.py`

`start.bat` 会进入项目根目录并执行：

```bat
venv312\Scripts\python.exe backend\launcher\start.py %*
```

启动器主要负责：

1. 清理旧进程。
2. 检查虚拟环境和依赖。
3. 分配 Flask、Qdrant HTTP、Qdrant gRPC 等端口。
4. 写入 `.port_config`。
5. 生成 Qdrant 配置。
6. 启动 Qdrant。
7. 启动 Flask 后端。
8. 启动 PyWebView/桌面 UI。

根目录 `server.py` 是一个“纯 Flask 测试服务器”，提供模拟状态和基础接口，不是正式主入口。

## 4. 端口和运行状态

重要约定：

- 后端接口测试和前端 E2E 都应读取 `.port_config`，不要硬编码端口。
- 当前 `.port_config` 格式类似：`18980,18981,18982,18983,18984`。
- 第一个端口通常是 Flask API 端口。
- Qdrant HTTP 端口通常是第二个端口。

Playwright 配置也遵循这个约定：

- 根目录 `playwright.config.ts` 从根目录 `.port_config` 读取第一个端口作为 `baseURL`。
- `web/playwright.config.ts` 也从项目根目录 `.port_config` 读取第一个端口。

## 5. 后端架构

正式后端入口是 `backend/app.py`。

它做了这些事：

- 设置 HuggingFace/Transformers 离线模式。
- 设置模型路径、embedding 维度、Qdrant 路径和 CPU/GPU 策略。
- 初始化 Flask、CORS、静态文件目录。
- 优先使用 `web/dist`，如果没有 dist 则回退到 `web`。
- 注册各个路由模块。
- 提供 SPA fallback，未匹配的前端路由回退到 `index.html`。
- 提供前端日志上报、UI 设置、控制台轮询等额外接口。

主要路由模块：

- `overview_routes.py`：模型、Qdrant、Flask、系统状态、后端重启、前端构建状态。
- `memory_routes.py`：记忆 CRUD、MCP 记忆接口、搜索历史、去重整理、实体图谱、事件相关接口。
- `wiki_routes.py`：Wiki 文件列表、索引、全量重建、索引进度、Wiki 搜索、Wiki 设置。
- `stream_routes.py`：操作流数据。
- `logs_routes.py`：日志读取。
- `settings_routes.py`：模型设置、配置读写、路径检查。
- `statusbar_routes.py`：底部状态栏数据。
- `stats_routes.py`：图表统计数据。

## 6. 模型和 Qdrant

项目依赖本地 embedding 模型：

- 模型：`BAAI/bge-m3`
- 默认路径：`models/bge-m3`
- 默认维度：`1024`
- 默认离线加载：`local_files_only=True`

后端启动后不能马上请求依赖模型的接口。应等待日志出现：

```text
[INFO] Model loaded successfully on cpu
```

AGENTS 约定中还要求：后端重启后等约 1 分钟让日志重新生成，再读取日志确认状态。

Qdrant 用于向量数据库：

- Qdrant 可执行文件通常位于项目内 `qdrant/qdrant.exe`。
- Qdrant 端口由启动器动态分配。
- 记忆集合名默认和配置相关，日志中可见 `mem0_memories`。

## 7. 前端架构

前端位于 `web/`，技术栈：

- Vue 3
- Vue Router
- Pinia
- Vite
- TypeScript
- ECharts
- Three.js
- force-graph / 3d-force-graph / AntV G6

前端主路由：

- `/overview`：总览。
- `/memory`：记忆。
- `/stream`：流。
- `/wiki`：Wiki。
- `/logs`：日志。
- `/settings`：设置。

根路径 `/` 重定向到 `/overview`。

前端请求封装在 `web/src/composables/useApi.ts`：

- API base 是 `window.location.origin`。
- 开发模式通过 Vite proxy 转发到 Flask。
- 生产/桌面模式由 Flask 直接托管 `web/dist`，API 与页面同源。

因此前端修改完成后必须执行构建：

```bash
cd web
npm run build
```

也可以通过后端接口触发：

```http
POST /overview/frontend/build
GET  /overview/frontend/build/status?build_id=...
```

## 8. 记忆与图谱能力

记忆核心功能在：

- `backend/routes/memory_routes.py`
- `backend/modules/brain/memory/`
- `backend/modules/brain/mem0_adapter.py`
- `backend/modules/brain/graph.py`
- `backend/modules/brain/dedup.py`
- `backend/modules/brain/rebuild_graph.py`

主要能力：

- 存储记忆：`POST /memory/store`
- 搜索记忆：`POST /memory/search`
- MCP 存储：`POST /memory/mcp/store`
- MCP 搜索：`POST /memory/mcp/search`
- 列表：`POST /memory/list`
- 删除：`POST /memory/delete`
- 更新：`POST /memory/update`
- 搜索历史：`GET/DELETE /memory/search-history`
- 去重整理：`/memory/organize/*`
- 实体统计、实体列表、实体管理、图谱可视化：`/memory/graph/*` 和 `/memory/entity/*`
- 事件时间线与事件测试接口：`/memory/events/*`

搜索结果会合并两类来源：

- 语义检索结果。
- 实体/图谱结果。

## 9. Wiki/RAG 能力

Wiki 路由在 `backend/routes/wiki_routes.py`，业务逻辑在 `backend/modules/Wiki/`。

主要接口：

- `POST /wiki/search`
- `GET /wiki/list`
- `POST /wiki/index`
- `POST /wiki/index-full`
- `GET /wiki/index-progress`
- `GET/POST /wiki/settings`

Wiki 使用 LightRAG 数据目录，日志中可见：

- `rag/lightrag_data/vdb_entities.json`
- `rag/lightrag_data/vdb_relationships.json`
- `rag/lightrag_data/vdb_chunks.json`

## 10. MCP 服务

`brain_mcp/` 提供 AiBrain Memory MCP 服务。

`.mcp.json` 中配置了：

- `brain`
- `wiki`

目前配置里这两个 MCP server 都是 `disabled: true`。

`brain_mcp/server.py` 只暴露两个工具：

- `store(text: str)`
- `search(query: str)`

`brain_mcp/tools.py` 会从环境变量 `FLASK_PORT` 或根目录 `.port_config` 读取 Flask 端口，然后调用后端接口：

- `/memory/mcp/store`
- `/memory/mcp/search`

## 11. 日志和重启

日志目录：

- 根目录 `logs/`
- 后端也有 `backend/logs/`

AGENTS 明确要求日志看根目录 `logs\`。

当前日志示例：

- `logs/flask_20260604_102239.log`
- `logs/ui_20260604_102249.log`

后端手动重启接口：

```http
POST /overview/flask/restart
```

这个接口会写入重启标志文件，实际重启应由启动器或进程管理器处理。修改后端文件后可使用该接口重启，但重启后要等模型加载完成，再访问模型相关接口。

## 12. 测试

测试分布：

- 根目录 `tests/`：包含 Playwright E2E、Python 单元/集成测试、图谱/记忆/Wiki 测试。
- `web/e2e/`：前端 E2E 测试。

根目录脚本：

```bash
npm test
npm run test:ui
npm run test:headed
```

前端 E2E 必须使用 Playwright，这是 AGENTS 明确要求。

前端修改后必须自动构建前端代码，构建命令：

```bash
cd web
npm run build
```

## 13. 当前工作区状态注意事项

理解项目时观察到当前 git 工作区不是完全干净：

- `.claude/rules/run.md` 有修改。
- `.agents/` 是未跟踪目录。
- `AGENTS.md` 是未跟踪文件。

后续修改代码时应避免覆盖或回滚这些已有改动，除非用户明确要求。

另外，AGENTS 提到项目计划目录是 `.Codex\plan\`，但当前根目录没有看到 `.codex` 或 `.Codex` 目录。若后续需要创建计划文档，应先确认目录名大小写和实际路径。

## 14. 后续开发时的实践规则

- 访问后端前先读 `.port_config`。
- 后端重启后先看 `logs/`，确认出现 `Model loaded successfully on cpu`。
- 涉及前端 UI 修改时，修改后运行 `web` 构建。
- 涉及前端页面验证时，使用 Playwright。
- 不要硬编码端口。
- 不要随意删除或覆盖 Qdrant、模型、RAG、日志和用户配置目录。
- 修改后端核心逻辑时优先看对应路由模块和 `backend/modules/` 中的业务实现。
- 修改前端页面时优先看对应 `web/src/views/<ViewName>/` 下的 ViewModel/组件拆分。
