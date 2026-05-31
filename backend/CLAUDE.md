# backend/ — Flask 3.1 后端

## 目录结构
```
backend/
├── app.py                   # 主入口 (Flask + PyWebView + 路由注册)
├── main.py                  # 启动脚本
├── download_model.py        # 模型下载
├── core/                    # 核心基础设施
│   ├── database.py          # SQLite: daily_stats / stream / search_history
│   ├── logger.py            # 日志系统 (按角色分文件, 归档保留3个)
│   ├── model.py             # ModelManager: Sentence Transformer 加载/卸载
│   └── settings.py          # ConfigManager: 系统配置单例
├── routes/                  # API 路由 (8 个模块)
│   ├── memory_routes.py     # 记忆 CRUD + 图操作 (~25 端点)
│   ├── overview_routes.py   # 系统概览卡片
│   ├── wiki_routes.py       # Wiki 搜索/索引/配置
│   ├── settings_routes.py   # 全局设置 API
│   ├── stats_routes.py      # 统计图表数据
│   ├── statusbar_routes.py  # 状态栏实时数据
│   ├── stream_routes.py     # 操作流记录
│   └── logs_routes.py       # 后端日志读取
├── modules/                 # 业务逻辑层
│   ├── brain/               # 记忆核心
│   │   ├── memory.py        # mem0 记忆 CRUD
│   │   ├── graph.py         # SQLite + NetworkX 实体枢纽图
│   │   ├── dedup.py         # 相似记忆去重 (SSE 流式)
│   │   ├── llm.py           # LLM 推理接口
│   │   ├── mem0_adapter.py  # mem0 客户端适配
│   │   ├── organizer.py     # 记忆整理 (聚类/精炼)
│   │   └── migrate.py       # 旧记忆迁移
│   ├── Wiki/wiki_mod.py     # LightRAG Wiki 模块
│   ├── Log/                 # 日志处理
│   ├── Settings/            # 设置处理
│   ├── Stats/               # 统计处理
│   └── SystemInfo/          # 系统信息
└── launcher/                # 进程管理
    ├── process_manager.py   # 多进程管理器 (Qdrant + Flask + WebView)
    ├── start_flask.py       # Flask 子进程 + watchdog 热重载
    ├── kill_old.py          # 清理旧进程
    ├── _boot_helper.py      # 启动辅助 (端口/依赖检查)
    └── start.py             # 通用启动入口
```

## 关键设计
- **单入口多路由**: `app.py` 注册 8 个路由蓝图
- **多实例隔离**: 端口通过 `.port_config` / 环境变量分配
- **离线模式**: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
- **sys.path 注入**: `brain_mcp/`, `rag/`, `mcp_servers/` 加入搜索路径

## 核心 API 端点
| 分组 | 端点 | 功能 |
|------|------|------|
| 记忆 | `/memory/store/search/list/delete/update` | CRUD |
| | `/memory/mcp/store/search` | MCP 异步接口 |
| 图谱 | `/memory/graph/entity/entities/visualization/link/merge` | 实体图 |
| | `/memory/entity/entitymgr/stats` | 实体管理 |
| 去重 | `/memory/organize/dedup/dedup/stream/refine/apply` | 去重 + SSE |
| 概览 | `/overview/model/qdrant/flask/system-info` | 系统状态 |
| Wiki | `/wiki/search/list/index/index-full/index-progress/settings` | 知识库 |
| 设置 | `/settings/api` / `/settings/reload-model` | 全局设置 |
| 其他 | `/chart-data /stream/api /logs/api /statusbar/api` | 统计/流/日志/状态 |
