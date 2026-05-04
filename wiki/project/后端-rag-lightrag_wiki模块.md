# 后端 - LightRAG Wiki 模块

## 概述
`rag/lightrag_wiki/` 是 AiBrain 的 Wiki 知识库引擎封装，基于 LightRAG 框架实现本地向量检索 + 知识图谱增强查询。

## 目录结构
```
rag/lightrag_wiki/
├── __init__.py      # 包入口（无导出）
├── config.py        # 配置管理（wiki.json 读写）
├── indexer.py       # 索引管理（增量索引 + 进度追踪）
└── rag_engine.py    # RAG 引擎封装（插入/查询/验证）
```

## config.py — 配置管理

### `load_wiki_config() -> dict`
**功能**：读取 wiki 配置（`~/.aibrain/config/wiki.json`）
**返回**：配置字典，字段：
```python
{
    "wiki_dir": "wiki",              # wiki 根目录（相对或绝对路径）
    "lightrag_dir": "rag/lightrag_data",  # LightRAG 数据目录
    "language": "Chinese",
    "chunk_token_size": 1200,
    "llm_provider": "openai",       # ollama / openai / anthropic
    "llm_model": "gpt-4o-mini",
    "llm_api_key": "...",
    "llm_base_url": "",
    "search_timeout": 120,
}
```

### `get_wiki_dir() -> str`
**功能**：获取 wiki 目录的绝对路径
- 如果配置中 `wiki_dir` 是绝对路径则直接返回
- 如果是相对路径则相对于 `AiBrain/` 项目根目录

### `get_lightrag_dir() -> str`
**功能**：获取 LightRAG 数据目录的绝对路径
- 如果配置中 `lightrag_dir` 是绝对路径则直接返回
- 如果是相对路径则相对于 `AiBrain/` 项目根目录

### `get_index_meta_path() -> str`
**功能**：获取索引元数据文件路径
- 路径：`{lightrag_dir}/.wiki_index_meta.json`
- 元数据记录每个文件的 MD5 和索引时间

---

## indexer.py — 索引管理

### `scan_wiki_files(wiki_dir: str) -> list[str]`
**功能**：扫描 wiki 目录下所有 `.md` 文件
**返回**：`.md` 文件的绝对路径列表（递归扫描）

### `sync_index() -> dict`
**功能**：增量同步索引（检测变化 + 更新 LightRAG）
**返回**：
```python
{
    "added": ["project/new.md"],      # 新增文件
    "updated": ["project/changed.md"], # MD5 变化的文件
    "deleted": ["project/removed.md"], # 已删除的文件
    "unchanged": 22,                  # 无变化的文件的数量
    "errors": [],                     # 索引失败的文件
}
```
**流程**：
1. 扫描 wiki 目录
2. 计算每个文件的 MD5，与 `.wiki_index_meta.json` 对比
3. 对新增/变化的文件调用 `_index_file()` 插入
4. 检测已删除的文件，从元数据中移除
5. 更新 `.wiki_index_meta.json`

### `index_single_file(filename: str) -> str`
**功能**：索引单个文件（写入后自动调用）
**参数**：`filename` 为相对于 wiki_dir 的文件名（如 `"project/test.md"`）
**返回**：索引结果描述（成功/失败原因）
**注意**：只更新元数据，不重新全量扫描

### `_index_file(abs_path: str, rel_path: str) -> bool`
**功能**：将单个 MD 文件内容插入 LightRAG，并通过 `aget_docs_by_track_id` 验证处理完成
**流程**：
1. `insert_document()` 入队（异步）
2. `_verify_vector_inserted()` 轮询 doc_status 直到 `status=processed`
**返回**：`True` = 插入并验证成功，`False` = 失败

### `get_index_progress() -> dict`
**功能**：获取当前索引进度
**返回**：
```python
{
    "running": False,           # 是否有索引任务在运行
    "done": 5,                  # 已完成的文件数
    "total": 10,                # 总共需要处理的文件数
    "current_file": "xxx.md",   # 当前正在处理的文件
    "status": "done",           # idle / running / done / error
    "result": {...},            # sync_index() 的返回结果
}
```

### `get_index_log(lines: int = 50) -> dict`
**功能**：获取最近的索引日志
**返回**：
```python
{
    "lines": ["[14:30:01] 索引: xxx.md (3/10)", ...],
    "total": 15,
}
```

### `_start_wiki_watcher()`
**功能**：启动 watchdog 文件监听（文件变化时自动增量索引）
- 监听 `.md` 文件的 create/modify/delete 事件
- 文件修改/新增时自动调用 `index_single_file()`
- 已在 `wiki_routes.py` 的 `wiki_list()` 中自动调用（惰性单例）

---

## rag_engine.py — RAG 引擎封装

### `get_rag() -> LightRAG`
**功能**：单例获取 LightRAG 实例（懒初始化）
**注意**：LightRAG 有已知的线程安全问题——单实例多次调用后可能永久阻塞。`query_wiki_context()` 为每个查询创建独立实例。

### `insert_document(text: str, file_path: str | None = None) -> str`
**功能**：插入文档到 LightRAG 索引
**参数**：
- `text`：文档内容
- `file_path`：文件路径（用于引用，不影响内容）

**返回**：`track_id` 字符串，用于追踪处理状态
**注意**：插入是异步的，方法返回后 LightRAG 后台仍在处理（嵌入/实体抽取/图谱构建）

### `query_wiki_context(question: str, mode: str = "hybrid") -> str`
**功能**：查询 wiki，返回检索到的上下文（**不经过 LLM 生成**）
**参数**：
- `question`：查询问题
- `mode`：`"naive"` | `"local"` | `"global"` | `"hybrid"` | `"mix"`

**返回**：检索到的文本片段（格式化的 JSON 字符串）
**特性**：每个查询创建独立 RAG 实例，避免线程阻塞

**各模式说明**：
| 模式 | 说明 |
|------|------|
| `naive` | 纯向量检索，最快 |
| `local` | 基于知识图谱局部查询 |
| `global` | 基于知识图谱全局查询 |
| `hybrid` | 向量 + 知识图谱混合 |
| `mix` | 混合 + 权重调优 |

### `delete_document(doc_id: str) -> dict`
**功能**：删除文档及其关联的知识图谱数据
**返回**：
```python
{
    "status": "success",
    "doc_id": "...",
    "message": "..."
}
```

### `reset_rag()`
**功能**：重置 RAG 单例（配置变更后调用）
- 将 `_rag_instance` 设为 `None`
- 下次调用 `get_rag()` 时会重新创建实例

### `_verify_vector_inserted(rel_path: str, track_id: str, timeout: int = 30) -> bool`
**功能**：验证文件是否已处理完成（异步轮询直到 status=processed 或超时）

`insert_document()` 是异步入队接口，LightRAG 后台线程处理完成后会更新 `doc_status` 存储。本函数通过 `aget_docs_by_track_id()` 轮询文档状态，等待其变为 `'processed'`。

**参数**：
- `rel_path`：文件相对路径（用于日志）
- `track_id`：`insert_document()` 返回的追踪 ID
- `timeout`：轮询超时秒数，默认 30 秒

**返回**：`True` = 文档已处理完成，`False` = 超时或失败

**DocProcessingStatus.status 枚举值**：
| 状态 | 说明 |
|------|------|
| `pending` | 等待处理 |
| `processing` | 处理中 |
| `preprocessed` | 预处理完成 |
| `processed` | 处理完成 |
| `failed` | 处理失败 |

---

## 内部机制

### 索引流程（_index_file）
```
_index_file(abs_path, rel_path)
  → insert_document(content, file_path=rel_path)
       返回 track_id
  → _verify_vector_inserted(rel_path, track_id, timeout=30)
       → 轮询 aget_docs_by_track_id(track_id)
       → 直到 status == 'processed' 或超时
  → 返回 True/False
```

### RAG 实例创建（_create_rag）
```
_create_rag()
  → load_wiki_config()        加载配置
  → _load_llm_config()         加载 LLM 配置（从 wiki.json 的 llm_* 字段）
  → _build_embedding_func()    构建 BGE-M3 embedding 函数
  → _build_llm_func()          根据 provider 构建 LLM 函数
  → LightRAG(embedding_func, llm_model_func, ...)
  → initialize_storages()      初始化向量存储和图存储
```

### LLM Provider 支持
| Provider | 说明 |
|----------|------|
| `openai` | OpenAI 兼容 API（默认） |
| `anthropic` | Anthropic 原生接口（Claude） |
| `ollama` | 本地 Ollama |
| 其他 | OpenAI 兼容（DeepSeek/MiniMax/Groq 等） |

---

## 相关模块
- **WikiManager** (`backend/modules/Wiki/wiki_mod.py`)：调用 `rag_engine` 和 `indexer`
- **wiki_routes** (`backend/routes/wiki_routes.py`)：提供 HTTP API 封装

---

*最后更新: 2026-05-04*
