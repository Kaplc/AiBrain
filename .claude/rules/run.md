# 执行规范

## MCP 工具参数说明

### brain_mcp (记忆系统)

| 工具 | 参数 | 说明 |
|------|------|------|
| `store_memory` | `text: str`, `link_entities?: list[str]` | 存储记忆到后端数据库，`link_entities` 用于关联已有实体 |
| `search_memory` | `query: str` | 搜索记忆，返回 `[{text, score}]` 列表 |

### 调用约定

- `brain_search` = `search_memory`（每次回复前必调用）
- `brain_store` = `store_memory`（每次对话结束后自动调用）
- 工具通过 `brain_mcp/tools.py` 暴露，实际调用后端 `/memory/mcp/*` 接口

## 规则

1. 每次回复前，先调用 `brain_search`（即 `search_memory`）查询记忆，根据结果决定如何回复
2. 回复内容须基于记忆中的上下文，禁止凭空编造
3. 每次对话结束后，将对话要点自动记录到记忆（`brain_store`），静默执行无需告知
4. 主动将经验总结沉淀到记忆，供后续参考