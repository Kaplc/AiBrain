# MCP search 返回结果移除 entities 字段

## 目标
MCP search 工具返回的每条结果中不再包含 `entities` 字段，只保留 `text` 和 `score`。

## 改动清单

### 1. `brain_mcp/tools.py` — search_memory 函数
- 移除返回结构中的 `"entities": r.get("entities", [])` 行
- 更新 docstring，去掉"关联实体"描述

### 2. `brain_mcp/server.py` — search 工具
- 更新 docstring，去掉"返回文本和相关性分数"中关于实体的描述（如有）

### 3. `brain_mcp/CLAUDE.md` — 文档
- search 工具说明去掉 entities 描述

### 4. `.claude/rules/run.md` — 调用约定
- `search_memory` 说明去掉 `entities`

## 不动的文件
- `backend/routes/memory_routes.py` — 后端接口返回的 entities 保留，前端仍需要
