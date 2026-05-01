# 后端 - Stream 模块（记忆流）

## 概述
`stream.py` 提供记忆流记录查询 API，从 stats_db 查询 MCP 调用和用户操作的历史记录。

## 文件位置
```
backend/modules/stream.py
```

## API 接口

### GET `/stream`
**查询参数**：
| 参数 | 说明 |
|------|------|
| `action` | 操作类型过滤（可选）：`store`、`search`、`delete`、`update` 等 |
| `days` | 按天数查询（优先，最多30天） |
| `limit` | 按条数查询（days 未指定时使用，最大200，默认30） |

**响应**：
```json
{
  "items": [
    {
      "id": 1,
      "action": "store",
      "content": "记忆文本...",
      "status": "done",
      "memory_id": "xyz789",
      "created_at": "2026-04-30T14:30:25"
    }
  ],
  "total": 12
}
```

**status 字段**（MCP store 异步操作）：
| 值 | 含义 |
|----|------|
| `pending` | 异步执行中 |
| `done` | 执行成功 |
| `error` | 执行失败 |

## 数据来源
`stats_db.query_stream(action, limit)` 和 `stats_db.query_stream_days(action, days)` 返回的记录列表。

## 前端集成
- **Steam 前端**：2秒轮询全量列表 + 1秒轮询 pending 状态
- **Memory MCP**：每次 store/search 调用自动记录

---
*最后更新: 2026-05-01*
