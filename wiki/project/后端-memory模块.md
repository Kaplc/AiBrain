# 后端 - Memory 模块

## 概述
`memory.py` 提供记忆的 CRUD、搜索、整理 API。区分用户操作和 MCP 操作：用户操作不记录到记忆流，MCP 操作异步执行并记录状态。

## 文件位置
```
backend/modules/memory.py
```

## API 接口

### POST `/store`
**功能**：用户手动存储记忆（**不记录到记忆流**）

**请求**：`{ "text": "记忆内容" }`
**响应**：`{ "result": "...", "stored_texts": [...] }`

### POST `/search`
**功能**：用户手动搜索（**不记录到记忆流**，非 MCP 的才记录搜索历史）

**请求**：`{ "query": "关键词" }`
**响应**：`{ "results": [{ "id": "uuid", "text": "...", "score": 0.85, "timestamp": "..." }] }`

**MCP 判断**：User-Agent 包含 `python` 或 `urllib` 则认为是 MCP 来源

### POST `/mcp/store`
**功能**：MCP 异步存储（**记录到记忆流，pending 状态**）

**请求**：`{ "text": "记忆内容" }`
**响应**：`{ "rowid": 123, "status": "pending" }`

**异步流程**：
1. 立即写入 stream（status=pending），返回 rowid
2. 后台线程执行 `store_memory()`
3. 用 LLM 提取的事实替换原始文本
4. 更新 stream 状态为 `done` 或 `error`

### POST `/mcp/search`
**功能**：MCP 搜索（**记录到记忆流**）

**请求**：`{ "query": "关键词" }`
**响应**：`{ "results": [...] }`

### POST `/list`
**请求**：`{ "offset": 0, "limit": 200 }`
**响应**：`{ "memories": [{ "id": "uuid", "text": "...", "timestamp": "..." }] }`

### POST `/delete`
**请求**：`{ "memory_id": "uuid" }`
**响应**：`{ "result": "deleted" }`

### POST `/update`
**功能**：同步更新记忆

### POST `/update-async`
**功能**：异步更新记忆（立即返回后台执行）

### GET `/search-history`
**响应**：`{ "history": [{ "query": "...", "created_at": "...", "count": 3 }] }`

### DELETE `/search-history`
**响应**：`{ "ok": true }`

## 记忆整理三步流程

### 第一步：去重分组
**POST `/organize/dedup`**
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

### 第二步：LLM 精炼
**POST `/organize/refine`**
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
**POST `/organize/apply`**
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
*最后更新: 2026-05-01*
