# 后端 - Wiki_mod 模块

## 概述
`wiki_mod.py` 提供 Wiki 知识库的搜索、文件管理、索引管理、配置管理 API，基于 LightRAG 框架实现。

## 文件位置
```
backend/modules/wiki_mod.py
```

## 延迟导入机制
RAG 引擎在首次请求时才会加载（不在模块级别 import）：
```python
def _get_rag_engine():
    from rag.lightrag_wiki.rag_engine import query_wiki_context
    from rag.lightrag_wiki.config import load_wiki_config
    from rag.lightrag_wiki.indexer import (
        index_single_file, sync_index, scan_wiki_files
    )
    return query_wiki_context, load_wiki_config, index_single_file, sync_index, scan_wiki_files
```

## API 接口

### POST `/wiki/search`
**请求**：
```json
{ "query": "关键词", "mode": "naive" }
```
**支持 mode**：`naive`（默认）、`hybrid`（带超时降级）

**响应**：
```json
{ "result": "搜索结果文本", "mode": "naive", "elapsed": 1.5 }
```

**超时降级逻辑**（仅 hybrid 模式）：
1. ThreadPoolExecutor 执行搜索，超时 `search_timeout`（默认30秒）
2. 超时 → `future.cancel()` → 降级 naive 模式
3. 最终响应 `mode` 字段标记为 `"naive(fallback)"`

### GET `/wiki/list`
**功能**：列出 wiki 目录所有文件

**响应**：
```json
{
  "files": [
    {
      "filename": "前端-overview模块.md",
      "abs_path": "E:\\Project\\AiBrain\\wiki\\project\\前端-overview模块.md",
      "size_bytes": 5120,
      "modified": 1746012345.123,
      "preview": "系统首页，展示模型...",
      "index_status": "synced"
    }
  ],
  "indexed": true
}
```

**index_status 值**：
| 值 | 含义 |
|----|------|
| `synced` | 文件已索引，与索引一致 |
| `out_of_sync` | 文件已修改，需重建索引 |
| `not_indexed` | 未索引 |

**indexed 判断**：检查 `rag/lightrag_data/.wiki_index_meta.json` 是否存在

### POST `/wiki/index`
**功能**：触发索引重建（异步，后台线程执行）

**响应**：
```json
{ "status": "started", "started_at": 0.05 }
```
如索引已在运行，返回 409 状态码：`{ "error": "索引任务正在进行中" }`

### GET `/wiki/index-progress`
**功能**：获取索引进度

**响应**：
```json
{ "status": "running", "done": 12, "total": 30, "current_file": "笔记.md" }
{ "status": "done", "done": 30, "total": 30 }
{ "status": "error", "error": "文件读取失败" }
```

### GET `/wiki/index-log`
**功能**：获取索引过程日志（内存缓冲区）

**参数**：`?lines=20`（默认20，最大500）

**响应**：
```json
{ "lines": ["[2026-04-30 14:30] 开始索引...", "[2026-04-30 14:30] 索引: 笔记.md (1/30)"] }
```

### GET `/wiki/log`
**功能**：读取后端日志文件中包含 wiki/RAG 关键词的行

**参数**：`?lines=200`（默认200，范围10-500）

**过滤关键词**：`wiki`, `RAG`, `lightrag`, `index`, `search`, `embed`

**响应**：
```json
{
  "lines": ["[2026-04-30 10:30] [RAG←] /wiki/search naive 完成"],
  "file": "app_20260430.log",
  "total_relevant": 150,
  "returned": 200
}
```

### GET/POST `/wiki/settings`
**GET**：获取 Wiki 配置（扁平存储转嵌套格式返回）

**POST**：保存 Wiki 配置（嵌套格式转扁平存储）

**扁平↔嵌套转换**（`_LLM_FLAT_MAP`）：
| 嵌套 key | 扁平 key |
|----------|---------|
| `provider` | `llm_provider` |
| `model` | `llm_model` |
| `api_key` | `llm_api_key` |
| `base_url` | `llm_base_url` |

**GET 响应示例**：
```json
{
  "wiki_dir": "wiki",
  "lightrag_dir": "rag/lightrag_data",
  "language": "Chinese",
  "chunk_token_size": 1200,
  "search_timeout": 30,
  "llm": {
    "provider": "minimax",
    "model": "MiniMax-M2.7",
    "api_key": "****",
    "base_url": "https://api.minimaxi.com/v1"
  }
}
```

**POST 只允许更新字段**：`wiki_dir`, `lightrag_dir`, `language`, `chunk_token_size`, `search_timeout`

## 日志标记规范
| 标记 | 含义 |
|------|------|
| `[API→]` | 收到请求 |
| `[API←]` | 返回响应 |
| `[API⚠]` | 降级/警告 |
| `[API✗]` | 错误 |
| `[RAG→]` | 调用 RAG 引擎 |
| `[RAG←]` | RAG 引擎返回 |

## 相关文件
| 文件 | 作用 |
|------|------|
| `rag/lightrag_wiki/rag_engine.py` | RAG 搜索引擎 |
| `rag/lightrag_wiki/config.py` | 配置读写 |
| `rag/lightrag_wiki/indexer.py` | 文件索引器、进度/日志管理 |
| `~/.aibrain/config/wiki.json` | Wiki 配置文件（扁平存储） |

## 前端集成
- **Wiki 前端**：消费 `/wiki/list`、`/wiki/index-progress`、`/wiki/index-log`、`/wiki/settings`
- **记忆流前端**：通过 Wiki MCP 工具调用 wiki_search/wiki_list

---
*最后更新: 2026-05-01*
