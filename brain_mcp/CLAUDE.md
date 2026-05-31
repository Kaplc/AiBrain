# brain_mcp/ — 核心 MCP 记忆服务器

## 概览
基于 FastMCP 的 MCP 服务器，提供记忆存储与检索能力，通过 HTTP 调用 Flask 后端 API 实现。

## 文件说明
| 文件 | 功能 |
|------|------|
| `server.py` | FastMCP 服务入口，暴露 2 个工具 |
| `tools.py` | 底层工具实现 (urllib → Flask API) |
| `embedding.py` | SentenceTransformer 嵌入模型管理 (bge-m3) + hash fallback |
| `config.py` | Pydantic-settings 配置 (Qdrant/embedding/搜索参数) |
| `__main__.py` | `python -m brain_mcp` 入口 |

## 暴露的工具 (FastMCP)
| 工具 | 参数 | 功能 |
|------|------|------|
| `store` | `text: str` | 存储记忆，LLM 自动提取事实 |
| `search` | `query: str` | 搜索记忆，返回 text + score |

## 关键设计
- **HTTP 桥接**: 通过 `urllib.request` 调用 Flask 的 `/memory/mcp/*` 端点
- **端口发现**: 从环境变量 `FLASK_PORT` 或 `.port_config` 文件读取
- **嵌入降级**: bge-m3 加载失败 → hash-based 伪嵌入 (graceful degradation)
- **离线模式**: 强制 `HF_HUB_OFFLINE=1`

## 配置 (config.py)
| 参数 | 默认值 | 说明 |
|------|--------|------|
| Qdrant host/port | localhost:6333 | 向量数据库 |
| collection | `mem0_memories` | 记忆集合名 |
| embedding model | `BAAI/bge-m3` (dim=1024) | 嵌入模型 |
| top_k | 10 | 搜索返回条数 |
| score_threshold | 0.5 | 相似度阈值 |
| forget_days | 100 | 遗忘周期 |
