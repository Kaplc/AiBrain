# 后端-settings_mod 模块

## 概述
`settings_mod.py` 是 AiBrain 后端的配置管理模块，负责处理系统设置、配置文件的读写、模型重载以及用户目录的配置文件管理。该模块提供了完整的配置管理 API，支持前端设置界面的所有功能。

## 主要功能

### 1. 配置管理器 (`AibrainConfigManager`)
- **单例模式**：确保全局唯一的配置管理实例
- **配置文件路径**：`~/.aibrain/config/mem0.json` 和 `~/.aibrain/config/wiki.json`
- **功能特性**：
  - 自动创建默认配置文件
  - 读取和写入配置文件
  - 配置数据的扁平化处理（处理嵌套结构）
  - 提供默认配置模板

### 2. 默认配置常量
- **DEFAULT_MEM0**：mem0 内存系统的默认配置
  - `wiki_dir`: Wiki 文档目录（默认："wiki"）
  - `lightrag_dir`: LightRAG 数据目录（默认："rag/lightrag_data"）
  - `language`: 语言设置（默认："Chinese"）
  - `chunk_token_size`: 分块大小（默认：1200）
  - LLM 相关配置（provider、model、api_key、base_url）
  - `search_timeout`: 搜索超时时间（默认：30秒）
- **DEFAULT_WIKI**：Wiki 系统的默认配置
  - `llm_provider`: LLM 提供商（默认："minimax"）
  - `llm_model`: 模型名称（默认："MiniMax-M2.7"）
  - `api_key`: API 密钥
  - `base_url`: API 基础地址（默认："https://api.minimaxi.com/v1"）
  - `collection_name`: 集合名称（默认："mem0_memories"）

### 3. API 端点

#### GET `/settings`
- **功能**：获取当前系统设置
- **返回**：JSON 格式的系统设置数据

#### GET `/config-info`
- **功能**：获取用户目录的配置文件信息
- **返回**：包含以下信息的 JSON：
  - 用户主目录路径
  - .aibrain 目录路径和大小
  - 配置文件（mem0.json, wiki.json）的内容和大小
  - 自动计算目录大小并格式化显示

#### POST `/settings`
- **功能**：保存系统设置
- **请求体**：JSON 格式的设置数据
- **支持字段**：`device`（设备设置）
- **返回**：保存结果

#### POST `/reload-model`
- **功能**：重新加载模型
- **请求体**：包含 `device` 字段的 JSON
- **工作流程**：
  1. 保存设备设置到配置文件
  2. 检查 GPU 可用性（如选择 GPU 模式但无 GPU 版 PyTorch 则警告）
  3. 在后台线程中重新加载模型
- **返回**：重载状态和可能的警告信息

#### POST `/save-aibrain-config`
- **功能**：保存 .aibrain/config 下的配置文件
- **请求体**：包含 `mem0` 和/或 `wiki` 配置的 JSON
- **返回**：保存结果

#### GET `/aibrain-config`
- **功能**：获取 aibrain 配置（动态扫描配置文件字段）
- **返回**：包含以下信息的 JSON：
  - `mem0`：当前 mem0 配置数据和字段定义
  - `wiki`：当前 wiki 配置数据和字段定义
  - **字段自动推断**：根据字段名自动判断类型
    - 目录类型：包含 dir/path/folder/directory 关键词
    - URL/密钥类型：包含 url/endpoint/api_key/key 关键词
    - 数字类型：包含 size/timeout/count/limit 关键词且值为整数
    - 文本类型：其他情况

#### POST `/check-path`
- **功能**：检查指定路径是否存在
- **请求体**：包含 `path` 字段的 JSON
- **返回**：`{"exists": true/false}`

#### POST `/select-directory`
- **功能**：通过系统对话框选择目录
- **实现**：使用 tkinter 文件对话框
- **默认路径**：项目根目录
- **返回**：选择的目录路径或空字符串

## 关键技术特性

### 1. 配置文件扁平化
- 处理嵌套的配置对象，将其展平为扁平字段
- 例如：`{"llm": {"provider": "openai"}}` → `{"llm_provider": "openai"}`

### 2. 智能字段类型推断
- 基于字段名关键词自动判断字段类型
- 支持类型：`text`、`dir`、`number`
- 便于前端渲染合适的输入控件

### 3. 线程安全的模型重载
- 使用后台线程加载模型，避免阻塞主线程
- 自动检测 GPU 可用性并提供警告

### 4. 跨平台目录选择
- 使用 tkinter 实现系统原生的目录选择对话框
- 自动设置项目根目录为默认路径

### 5. 配置完整性检查
- 自动创建缺失的配置目录和文件
- 提供合理的默认值

## 依赖关系
- **Flask**：路由处理
- **torch**：GPU 可用性检查
- **tkinter**：目录选择对话框（可选）
- **os**、**json**、**threading**：系统基础功能

## 使用示例

### 获取配置信息
```bash
curl http://localhost:5000/config-info
```

### 保存 mem0 配置
```bash
curl -X POST http://localhost:5000/save-aibrain-config \
  -H "Content-Type: application/json" \
  -d '{"mem0": {"llm_provider": "openai", "llm_model": "gpt-4o-mini"}}'
```

### 重新加载模型（GPU模式）
```bash
curl -X POST http://localhost:5000/reload-model \
  -H "Content-Type: application/json" \
  -d '{"device": "gpu"}'
```

## 配置文件示例

### mem0.json
```json
{
  "wiki_dir": "wiki",
  "lightrag_dir": "rag/lightrag_data",
  "language": "Chinese",
  "chunk_token_size": 1200,
  "llm_provider": "openai",
  "llm_model": "gpt-4o-mini",
  "llm_api_key": "sk-...",
  "llm_base_url": "",
  "search_timeout": 30
}
```

### wiki.json
```json
{
  "llm_provider": "minimax",
  "llm_model": "MiniMax-M2.7",
  "api_key": "...",
  "base_url": "https://api.minimaxi.com/v1",
  "collection_name": "mem0_memories"
}
```

## 注意事项
1. **GPU 检测**：如果选择 GPU 模式但未安装 GPU 版 PyTorch，会返回警告信息
2. **配置文件位置**：配置文件存储在用户主目录的 `.aibrain/config/` 下
3. **线程安全**：模型重载在后台线程执行，不会阻塞 API 响应
4. **跨平台兼容**：目录选择功能依赖 tkinter，在无 GUI 环境中可能不可用
5. **字段推断**：字段类型推断基于关键词匹配，特殊字段名可能需要手动处理