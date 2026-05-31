# 精简 brain_mcp 工具：只保留 store 和 search

## 目标
移除 `entity_lookup` 和 `list_entities` 两个 MCP 工具，只保留 `store` 和 `search`。

## 改动清单

### 1. `brain_mcp/server.py` — 删除多余工具注册
- 移除 `entity_lookup` 工具函数（第63-71行）
- 移除 `list_entities` 工具函数（第74-77行）
- 移除 `_graph_call` 辅助函数（第25-38行，仅 entity_lookup 使用）
- 移除 `from .tools import store_memory, search_memory, list_entities` 中的 `list_entities`

### 2. `brain_mcp/tools.py` — 删除多余底层函数
- 移除 `search_entity` 函数（第89-98行）
- 移除 `list_entities` 函数（第101-106行）

### 3. `brain_mcp/CLAUDE.md` — 更新文档
- 工具表从 4 个改为 2 个，移除 entity_lookup 和 list_entities 行

### 4. `.claude/rules/run.md` — 更新调用约定
- 移除工具表中的 `search_entity` 和 `list_entities` 行
- 更新说明文字

## 不动的文件
- `backend/routes/memory_routes.py` — 后端路由全部保留，前端/其他模块仍在使用
- `brain_mcp/tools.py` 中的 `store_memory` 和 `search_memory` — 保留
