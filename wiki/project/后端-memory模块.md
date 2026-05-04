# 后端 - Memory 模块

## 概述
`memory.py` 提供记忆的 CRUD、搜索、整理 API。区分用户操作和 MCP 操作：用户操作不记录到记忆流，MCP 操作异步执行并记录状态。

## 文件位置
```
backend/modules/memory.py
```

## API 接口

### POST `/memory/store`
**功能**：用户手动存储记忆（**不记录到记忆流**）
**代码位置**：`memory_routes.py:16`

**请求**：`{ "text": "记忆内容" }`
**响应**：`{ "result": "...", "stored_texts": [...] }`

### POST `/memory/search`
**功能**：用户手动搜索（**不记录到记忆流**，非 MCP 的才记录搜索历史）
**代码位置**：`memory_routes.py:33`

**请求**：`{ "query": "关键词" }`
**响应**：`{ "results": [{ "id": "uuid", "text": "...", "score": 0.85, "timestamp": "..." }] }`

**MCP 判断**：User-Agent 包含 `python` 或 `urllib` 则认为是 MCP 来源

### POST `/memory/mcp/store`
**功能**：MCP 异步存储（**记录到记忆流，pending 状态**）
**代码位置**：`memory_routes.py:50`

**请求**：`{ "text": "记忆内容" }`
**响应**：`{ "rowid": 123, "status": "pending" }`

**异步流程**：
1. 立即写入 stream（status=pending），返回 rowid
2. 后台线程执行 `store_memory()`
3. 用 LLM 提取的事实替换原始文本
4. 更新 stream 状态为 `done` 或 `error`

### POST `/memory/mcp/search`
**功能**：MCP 搜索（**记录到记忆流**）
**代码位置**：`memory_routes.py:75`

**请求**：`{ "query": "关键词" }`
**响应**：`{ "results": [...] }`

### POST `/memory/list`
**代码位置**：`memory_routes.py:88`
**请求**：`{ "offset": 0, "limit": 200, "source": "user" | "mcp" }`
**响应**：`{ "memories": [{ "id": "uuid", "text": "...", "timestamp": "..." }] }`

### POST `/memory/delete`
**代码位置**：`memory_routes.py:103`
**请求**：`{ "memory_id": "uuid" }`
**响应**：`{ "result": "deleted" }`

### POST `/memory/update`
**功能**：同步更新记忆
**代码位置**：`memory_routes.py:117`

### POST `/memory/update-async`
**功能**：异步更新记忆（立即返回后台执行）
**代码位置**：`memory_routes.py:133`

### POST `/memory/organize`
**功能**：一键整理记忆（搜索 → 分类 → 删旧 → 存新，全自动）

**请求**：`{ "query": "主题词" }`
**响应**：
```json
{
  "query": "主题词",
  "total_found": 4,
  "categories": { "user": [...], "project": [...], ... },
  "organized": [{ "category": "user", "count": 2, "summary": "..." }],
  "deleted_ids": ["id1", "id2"],
  "organized_text": "# 记忆整理 - 主题: ...",
  "individual_memories": [{ "id": "...", "text": "[user] ...", "category": "user" }],
  "new_memory_ids": ["new_id1", ...],
  "new_memory_id": "new_id1"
}
```

### GET `/memory/search-history`
**代码位置**：`memory_routes.py:158`
**响应**：`{ "history": [{ "query": "...", "created_at": "...", "count": 3 }] }`

### DELETE `/memory/search-history`
**代码位置**：`memory_routes.py:166`
**响应**：`{ "ok": true }`

## 记忆整理三步流程

### 第一步：去重分组（同步）
**POST `/memory/organize/dedup`**
**代码位置**：`memory_routes.py:187`
```json
{ "similarity_threshold": 0.85 }
```
```json
{
  "groups": [
    {
      "similarity": 0.92,
      "memories": [
        { "id": "abc", "text": "记忆A" },
        { "id": "def", "text": "记忆B" }
      ]
    }
  ],
  "total_memories": 50,
  "grouped_count": 12
}
```

### 第一步（变体）：流式去重分析（新增）
**POST `/memory/organize/dedup/stream`** — SSE 流式接口，实时推送进度
**代码位置**：`memory_routes.py:198`

**请求**：`{ "similarity_threshold": 0.85, "batch_size": 30 }`

**SSE 响应**：每条消息格式 `data: {...}\n\n`
```json
// 定期推送已发现的组
{ "type": "batch", "found": 5, "total": 100, "groups": [...] }

// 分析完成
{ "type": "done", "total": 100, "grouped": 30, "ungrouped": 70, "groups": [...] }

// 中途停止
{ "type": "stopped", "found": 12, "groups": [...] }

// 异常
{ "type": "error", "error": "错误信息" }
```

**控制接口**：
| 接口 | 代码位置 | 说明 |
|------|---------|------|
| `POST /memory/organize/dedup/pause` | `memory_routes.py:229` | 暂停去重分析（设置 `_dedup_pause_flag`） |
| `POST /memory/organize/dedup/resume` | `memory_routes.py:236` | 恢复去重分析（清除 `_dedup_pause_flag`） |
| `POST /memory/organize/dedup/stop` | `memory_routes.py:243` | 停止去重分析（设置 `_dedup_stop_flag`） |

### 第二步：LLM 精炼
**POST `/memory/organize/refine`**
**代码位置**：`memory_routes.py:251`
```json
{ "groups": [{ "similarity": 0.92, "memories": [...] }] }
```
```json
{
  "refined": [
    {
      "refined_text": "精炼后的记忆...",
      "category": "reference",
      "original_ids": ["abc", "def"]
    }
  ]
}
```

### 第三步：写入
**POST `/memory/organize/apply`**
**代码位置**：`memory_routes.py:264`
```json
{ "items": [{ "delete_ids": ["abc", "def"], "new_text": "精炼结果", "category": "reference" }] }
```
```json
{ "added": 1, "deleted": 2, "applied": 1 }
```

## 相关模块
- **brain/memory.py**：实际业务逻辑（store_memory, search_memory 等）
- **brain/dedup.py**：去重分组（dedup_memories）
- **brain/llm.py**：LLM 精炼（refine_group）
- **brain/organizer.py**：组织整理（organize_memories）

---
*最后更新: 2026-05-04*
