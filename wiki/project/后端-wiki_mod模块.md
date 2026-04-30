# 后端 - Wiki_mod 模块

## 概述
Wiki_mod 模块是 AiBrain 系统的知识库管理模块，基于 LightRAG 框架实现智能文档搜索、索引管理和配置管理。该模块提供了完整的知识库操作 API，支持多种搜索模式、文档列表查看、索引同步和日志查询功能。

## 主要功能

### 1. 智能文档搜索
- **多模式搜索**：支持 naive、hybrid、local、global、mix 五种搜索模式
- **超时降级**：复杂搜索模式超时自动降级到 naive 模式
- **语义理解**：基于 RAG（Retrieval-Augmented Generation）的智能搜索
- **结果优化**：返回与查询最相关的文档片段

### 2. 文档管理
- **文件列表**：扫描 wiki 目录，获取所有文档文件信息
- **文件预览**：提供文档前 200 字符的预览内容
- **元数据获取**：文件大小、修改时间、相对路径等信息
- **目录结构**：支持嵌套目录结构的文档管理

### 3. 索引管理
- **全量索引同步**：扫描 wiki 目录，更新向量索引
- **增量更新**：检测文件变化，只更新变更文件
- **索引状态**：返回添加、更新、删除、未变更的文件统计
- **手动触发**：支持手动触发索引重建

### 4. 日志查询
- **相关日志过滤**：只返回包含 wiki/RAG/搜索关键词的日志行
- **多日志文件支持**：自动检测最新的日志文件
- **行数控制**：支持自定义返回行数（10-500 行）
- **文件信息**：返回日志文件名和相关统计

### 5. 配置管理
- **配置读取**：获取当前 Wiki 配置，包括 LLM 设置
- **配置保存**：更新 Wiki 配置，支持扁平化和嵌套格式转换
- **敏感信息保护**：API 密钥等敏感信息返回时隐藏
- **配置验证**：只允许更新特定字段，防止配置损坏

## API 接口

### POST `/wiki/search`
**功能**：搜索 Wiki 知识库

**请求体**：
```json
{
  "query": "搜索关键词",
  "mode": "naive"  // naive, hybrid, local, global, mix
}
```

**响应示例**：
```json
{
  "result": "搜索结果的文本内容",
  "mode": "naive",
  "elapsed": 1.5
}
```

**搜索模式说明**：
- **naive**：基础模式，快速返回结果
- **hybrid**：混合模式，结合多种策略（可能超时降级）
- **local**：本地上下文优先模式
- **global**：全局语义模式
- **mix**：混合优化模式

**超时降级机制**：
1. 如果指定模式超时（默认 30 秒），自动取消任务
2. 降级到 naive 模式重新搜索
3. 返回降级后的结果，并标记模式为 "naive(fallback)"

### GET `/wiki/list`
**功能**：列出 Wiki 目录中的所有文档

**响应示例**：
```json
{
  "files": [
    {
      "filename": "前端-overview模块.md",
      "abs_path": "C:/AiBrain/wiki/前端-overview模块.md",
      "size_bytes": 4521,
      "modified": 1745934625.123456,
      "preview": "# 前端 - Overview 模块..."
    }
  ]
}
```

**字段说明**：
- `filename`：相对 wiki 目录的文件名
- `abs_path`：绝对路径
- `size_bytes`：文件大小（字节）
- `modified`：修改时间戳
- `preview`：文件前 200 字符的预览内容

### POST `/wiki/index`
**功能**：同步 Wiki 索引（全量更新）

**响应示例**：
```json
{
  "added": ["新文件1.md", "新文件2.md"],
  "updated": ["更新文件.md"],
  "deleted": ["删除文件.md"],
  "unchanged": 25,
  "total_files": 28
}
```

**索引过程**：
1. 扫描 wiki 目录，获取所有 Markdown 文件
2. 与现有索引比较，识别变化
3. 对新文件创建向量索引
4. 对更新文件重新索引
5. 删除已不存在文件的索引

### GET `/wiki/log`
**功能**：获取 Wiki 相关的日志

**查询参数**：
- `lines`：返回行数，默认 200，范围 10-500

**响应示例**：
```json
{
  "lines": [
    "[2025-04-29 10:30:25] [INFO] [API→] /wiki/search | query=人工智能",
    "[2025-04-29 10:30:26] [INFO] [RAG→] /wiki/search 调用 naive 模式"
  ],
  "file": "app_20250429.log",
  "total_relevant": 150,
  "returned": 100
}
```

**日志过滤关键词**：wiki, RAG, lightrag, index, search, embed

### GET `/wiki/settings`
**功能**：获取 Wiki 配置

**响应示例**：
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
    "base_url": "https://api.minimaxi.com/v1"
  }
}
```

**敏感信息处理**：API 密钥返回时显示为 "****"

### POST `/wiki/settings`
**功能**：保存 Wiki 配置

**请求体**：
```json
{
  "wiki_dir": "new_wiki",
  "lightrag_dir": "rag/new_data",
  "language": "English",
  "chunk_token_size": 1000,
  "search_timeout": 60,
  "llm": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "sk-...",
    "base_url": "https://api.openai.com/v1"
  }
}
```

**响应示例**：
```json
{
  "ok": true
}
```

**配置保护**：
- 只允许更新特定字段：wiki_dir, lightrag_dir, language, chunk_token_size, search_timeout
- LLM 配置支持嵌套格式，存储时扁平化
- API 密钥为空时保留原值

## 技术实现

### 模块结构
```
backend/modules/wiki_mod.py
├── register(app, stats_db=None)          # 注册所有路由
├── wiki_search()                         # 文档搜索
├── wiki_list()                           # 文档列表
├── wiki_index()                          # 索引同步
├── wiki_log()                            # 日志查询
└── wiki_settings()                       # 配置管理
```

### 延迟导入机制
为了避免启动时加载沉重的 RAG 模块，采用延迟导入策略：

```python
def _get_rag_engine():
    from rag.lightrag_wiki.rag_engine import query_wiki_context
    from rag.lightrag_wiki.config import load_wiki_config
    from rag.lightrag_wiki.indexer import (
        index_single_file, sync_index, scan_wiki_files
    )
    return query_wiki_context, load_wiki_config, index_single_file, sync_index, scan_wiki_files
```

### 搜索超时处理
1. **线程池执行**：使用 `ThreadPoolExecutor` 执行搜索任务
2. **超时检测**：设置 config 中的 `search_timeout`（默认 30 秒）
3. **任务取消**：超时后立即取消 Future，防止线程泄漏
4. **优雅降级**：降级到 naive 模式继续搜索

### 配置格式转换
**扁平化存储**（在配置文件中）：
```json
{
  "llm_provider": "minimax",
  "llm_model": "MiniMax-M2.7",
  "llm_api_key": "sk-...",
  "llm_base_url": "https://api.minimaxi.com/v1"
}
```

**嵌套化返回**（给前端 API）：
```json
{
  "llm": {
    "provider": "minimax",
    "model": "MiniMax-M2.7",
    "api_key": "****",
    "base_url": "https://api.minimaxi.com/v1"
  }
}
```

### 日志记录规范
模块使用统一的日志标记规范：

| 标记 | 含义 | 示例 |
|------|------|------|
| `[API→]` | 收到 API 请求 | `[API→] /wiki/search | query=人工智能` |
| `[API←]` | 返回 API 响应 | `[API←] /wiki/list 完成 | total=0.5s files_count=15` |
| `[API⚠]` | 降级/警告 | `[API⚠] /wiki/search hybrid 超时，降级 naive` |
| `[API✗]` | 错误 | `[API✗] /wiki/search 失败: ConnectionError` |
| `[RAG→]` | 调用 RAG 引擎 | `[RAG→] /wiki/search 调用 naive 模式` |
| `[RAG←]` | RAG 引擎返回 | `[RAG←] /wiki/search naive 完成 | rag_elapsed=1.2s` |

## 配置管理

### 配置文件位置
- **用户配置**：`~/.aibrain/config/wiki.json`
- **默认配置**：模块内定义的 `DEFAULT_WIKI` 常量
- **项目配置**：可通过 API 动态更新

### 可配置字段
1. **目录设置**：
   - `wiki_dir`：Wiki 文档目录（默认 "wiki"）
   - `lightrag_dir`：LightRAG 数据目录（默认 "rag/lightrag_data"）

2. **处理参数**：
   - `language`：文档语言（默认 "Chinese"）
   - `chunk_token_size`：文本分块大小（默认 1200）
   - `search_timeout`：搜索超时时间（默认 30 秒）

3. **LLM 配置**：
   - `provider`：LLM 提供商（如 minimax, openai）
   - `model`：模型名称
   - `api_key`：API 密钥
   - `base_url`：API 基础地址

### 配置验证
- **字段白名单**：只允许更新特定字段
- **类型检查**：确保配置值类型正确
- **路径存在性**：可选的路径验证
- **API 密钥保护**：存储时完整保存，返回时隐藏

## 错误处理

### 异常处理策略
1. **搜索异常**：捕获所有异常，返回错误信息，不崩溃
2. **配置异常**：配置文件损坏时使用默认配置
3. **文件异常**：文件不存在或权限问题时返回空列表
4. **索引异常**：索引失败时返回错误，不影响服务

### 降级机制
1. **超时降级**：复杂搜索模式超时后降级到 naive 模式
2. **配置降级**：自定义配置失败时使用默认配置
3. **资源降级**：内存不足时减少处理数据量

### 日志记录
- **详细跟踪**：记录每个请求的关键参数和耗时
- **性能监控**：记录 RAG 引擎调用时间和结果长度
- **错误诊断**：记录异常堆栈，便于排查问题
- **状态跟踪**：记录索引更新和文件变化

## 性能考虑

### 优化措施
1. **延迟加载**：RAG 引擎按需加载，减少启动时间
2. **缓存机制**：配置和文件列表适当缓存
3. **超时控制**：防止长时间运行的搜索阻塞服务
4. **并行处理**：索引更新支持并行处理文件

### 资源消耗
- **内存使用**：分块处理大文件，避免一次性加载
- **CPU 使用**：向量计算可能消耗较多 CPU 资源
- **磁盘 I/O**：索引文件存储在本地，需要磁盘空间
- **网络带宽**：LLM API 调用需要网络连接

## 使用场景

### 知识库搜索
- **技术文档查询**：快速查找项目文档和指南
- **代码规范检索**：查找编码规范和最佳实践
- **问题解决方案**：搜索历史问题和解决方案

### 文档管理
- **文档浏览**：查看所有可用文档和预览
- **文档更新**：检测文档变化并更新索引
- **版本跟踪**：通过修改时间跟踪文档版本

### 系统维护
- **索引维护**：定期同步索引，保持搜索准确性
- **日志监控**：查看系统运行状态和错误信息
- **配置调整**：根据需求调整搜索参数和 LLM 设置

## 相关模块

### 前端模块
- **Wiki 模块**：主要消费者，提供知识库搜索界面
- **Settings 模块**：Wiki 配置管理界面

### 后端模块
- **RAG 引擎**：`rag/lightrag_wiki/` 实际搜索实现
- **配置管理**：`settings_mod.py` 共享配置管理逻辑
- **日志系统**：`core/logger.py` 统一的日志记录

### 基础设施
- **LightRAG 框架**：提供 RAG 核心功能
- **向量数据库**：存储文档向量索引
- **LLM 服务**：提供语义理解和文本生成

## 扩展计划

### 短期改进
1. **更多搜索过滤器**：按文件类型、修改时间过滤
2. **搜索结果高亮**：在结果中高亮显示匹配关键词
3. **搜索历史**：记录用户搜索历史，提供热门搜索
4. **相关文档推荐**：基于当前文档推荐相关文档

### 长期规划
1. **多知识库支持**：支持多个独立的知识库
2. **文档协作**：支持多人协作编辑和评论
3. **知识图谱**：构建文档之间的关联图谱
4. **自动化摘要**：自动生成文档摘要和关键词