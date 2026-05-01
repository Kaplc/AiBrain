# 后端 - Settings_mod 模块

## 概述
`settings_mod.py` 提供系统设置、模型重载、配置文件读写 API。配置存储在 `~/.aibrain/config/` 下。

## 文件位置
```
backend/modules/settings_mod.py
```

## 配置文件

### mem0.json 存储格式（扁平）
```json
{
  "wiki_dir": "wiki",
  "lightrag_dir": "rag/lightrag_data",
  "language": "Chinese",
  "chunk_token_size": 1200,
  "llm_provider": "minimax",
  "llm_model": "MiniMax-M2.7",
  "llm_api_key": "sk-...",
  "llm_base_url": "https://api.minimaxi.com/v1",
  "search_timeout": 30
}
```

### wiki.json 存储格式（扁平）
```json
{
  "llm_provider": "minimax",
  "llm_model": "MiniMax-M2.7",
  "api_key": "sk-...",
  "base_url": "https://api.minimaxi.com/v1",
  "collection_name": "mem0_memories"
}
```

## API 接口

### GET `/settings`
**功能**：获取当前设备设置
**响应**：`{ "device": "cuda" }`

### POST `/settings`
**功能**：保存设备设置
**请求**：`{ "device": "gpu" }`

### POST `/reload-model`
**功能**：重载 embedding 模型

**请求**：`{ "device": "gpu" }`
**响应**：`{ "result": "模型重载中，设备: gpu", "warning": "选择了 GPU 模式但未安装 GPU 版 PyTorch" }`（如有警告）

**实现**：后台线程执行 `model_mgr.load(device)`

### GET `/aibrain-config`
**功能**：获取动态配置表单 schema

**响应**：
```json
{
  "mem0": {
    "data": { /* 实际配置数据 */ },
    "fields": [
      { "key": "wiki_dir", "label": "wiki_dir", "type": "dir", "value": "wiki", "default": "wiki" },
      { "key": "chunk_token_size", "label": "chunk_token_size", "type": "number", "value": 1200, "default": 1200 }
    ]
  },
  "wiki": { ... }
}
```

**字段类型推断**：
| 关键词 | 类型 |
|--------|------|
| `dir`/`path`/`folder`/`directory` | `dir` |
| `url`/`endpoint`/`api_key`/`key` | `text` |
| `size`/`timeout`/`count`/`limit`（int） | `number` |
| 其他 | `text` |

### POST `/save-aibrain-config`
**功能**：保存 mem0 或 wiki 配置

**请求**：
```json
{
  "mem0": { "wiki_dir": "new_wiki", "chunk_token_size": 1000 },
  "wiki": { "llm_provider": "openai" }
}
```
**响应**：`{ "result": { "mem0": "已保存", "wiki": "已保存" } }`

### GET `/config-info`
**功能**：获取配置文件信息（路径、大小、内容）

### POST `/check-path`
**请求**：`{ "path": "C:\\path\\to\\dir" }`
**响应**：`{ "exists": true }`

### POST `/select-directory`
**功能**：通过 tkinter 原生对话框选择目录

**响应**：`{ "path": "C:\\selected\\path" }`（用户取消时 path 为空字符串）

## AibrainConfigManager
单例配置管理器：
- `read_mem0()` / `write_mem0()`：读写 mem0.json
- `read_wiki()` / `write_wiki()`：读写 wiki.json（嵌套转扁平存储）
- `init_default_configs()`：文件不存在时创建默认配置

## 前端集成
- **Settings 前端**：消费所有端点，动态渲染表单
- **Overview 前端**：消费 `/reload-model`

---
*最后更新: 2026-05-01*
