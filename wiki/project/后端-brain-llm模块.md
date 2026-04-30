# 后端-brain-llm 模块

## 概述
`llm.py` 是 AiBrain 大脑模块中的 LLM 调用封装组件，负责通过 OpenAI 兼容接口统一调用各种大型语言模型。该模块专为记忆整理任务设计，能够将多条语义相似的记忆合并为一条更精炼、更完整的描述，并自动分类记忆类型。

## 核心功能

### 1. 记忆合并精炼
- **输入**：一组语义相似的记忆
- **处理**：调用 LLM 合并精炼
- **输出**：单条精炼后的记忆，附带分类标签

### 2. 多提供商支持
- 复用 mem0 配置，支持多种 LLM 提供商
- 统一接口调用，简化集成复杂度

### 3. 自动记忆分类
自动判断记忆类型，从5个预定义类别中选择：
- **user**：用户个人信息、偏好、习惯、感受
- **feedback**：用户反馈、建议、意见、改进想法  
- **project**：项目开发、代码、功能实现、技术任务
- **reference**：文档、链接、参考资料、学习笔记
- **ai**：AI 自身的行为、偏好、记忆、经验总结

## 系统提示词

### SYSTEM_PROMPT
```text
你是一个记忆整理助手。你的任务是将多条语义相似的记忆合并为一条更精炼、更完整的描述。

规则：
1. 合并时保留所有关键信息，不遗漏重要细节
2. 去除重复表述，使文本更简洁
3. 保持原有时序信息（如日期、时间顺序）
4. 用中文输出
5. 如果记忆之间存在矛盾，保留最新的信息，并标注矛盾点
6. 自动判断记忆类型，从以下5类中选择：user/feedback/project/reference/ai
   - user: 用户个人信息、偏好、习惯、感受
   - feedback: 用户反馈、建议、意见、改进想法
   - project: 项目开发、代码、功能实现、技术任务
   - reference: 文档、链接、参考资料、学习笔记
   - ai: AI 自身的行为、偏好、记忆、经验总结

输出格式（严格遵守JSON）：
{"refined_text": "合并后的精炼文本", "category": "类型"}
```

## 主要函数

### `refine_group(memories)`
- **功能**：对一组相似记忆调用 LLM 合并精炼
- **参数**：`memories` - 记忆列表，格式 `[{"id": "...", "text": "..."}, ...]`
- **返回**：精炼结果字典
- **工作流程**：
  1. 提取原始记忆的 ID 和文本
  2. 调用 `_build_user_prompt` 构建用户提示词
  3. 调用 `call_llm` 处理
  4. 调用 `_parse_llm_response` 解析 LLM 响应
  5. 返回精炼结果（成功时）或降级拼接（异常时）

### `call_llm(system_prompt, user_prompt, timeout=30)`
- **功能**：调用 LLM，返回原始文本响应
- **参数**：
  - `system_prompt`：系统提示词
  - `user_prompt`：用户提示词
  - `timeout`：超时时间（秒），默认30
- **返回**：LLM 的原始文本响应
- **固定参数**：`temperature=0.3`，`max_tokens=1024`

### `_load_llm_config()`
- **功能**：从 mem0 配置读取 LLM 参数
- **返回**：包含 provider、model、api_key、base_url 的字典
- **数据源**：通过 `modules.brain.mem0_adapter.load_mem0_config()` 加载

### `_build_user_prompt(memories)`
- **功能**：构建用户提示词
- **参数**：记忆列表
- **返回**：格式化后的提示词文本
- **格式**：
  ```
  请合并以下 N 条相似记忆：
  
  [1] 记忆内容1
  [2] 记忆内容2
  ...
  
  请输出JSON格式的合并结果。
  ```

### `_parse_llm_response(raw)`
- **功能**：解析 LLM 返回的 JSON，支持容错提取
- **参数**：LLM 原始响应文本
- **返回**：解析后的字典
- **解析策略**（按优先级）：
  1. 直接 JSON 解析
  2. 提取 ```json ... ``` 代码块
  3. 提取第一个包含 `"refined_text"` 的 JSON 对象
  4. 降级：原始文本作为 refined_text，category="reference"

## 配置管理

### 1. 配置来源
- 通过 `modules.brain.mem0_adapter.load_mem0_config()` 加载
- **默认值**：provider=openai，model=gpt-4o-mini，api_key=""，base_url=""

### 2. base_url 自动推断
- **Ollama**：`http://localhost:11434/v1`
- **LM Studio**：`http://localhost:1234/v1`
- 其他提供商需在配置中显式指定 base_url

### 3. API Key 处理
- 空 API Key 时使用 `"dummy"` 作为占位，支持本地模型（Ollama 等）

## 技术实现

### 1. OpenAI 兼容接口
- 使用 `openai` 库的 `OpenAI` 客户端
- 通过 `base_url` 支持不同提供商
- 调用 `client.chat.completions.create()` 方法

### 2. 本地模型支持
- **Ollama**：自动设置 `base_url = "http://localhost:11434/v1"`
- **LM Studio**：自动设置 `base_url = "http://localhost:1234/v1"`

### 3. 超时与降级
- 默认30秒超时
- 异常时降级为简单文本拼接（`" | ".join(original_texts)`）

## 数据结构

### 输入格式
```python
[
    {"id": "记忆ID1", "text": "用户喜欢在早上喝咖啡"},
    {"id": "记忆ID2", "text": "用户习惯每天早晨喝一杯美式咖啡"}
]
```

### 成功输出格式
```python
{
    "original_ids": ["记忆ID1", "记忆ID2"],
    "original_texts": ["用户喜欢在早上喝咖啡", "用户习惯每天早晨喝一杯美式咖啡"],
    "refined_text": "用户习惯每天早晨喝一杯美式咖啡",
    "category": "user",
    "refined": True
}
```

### 失败输出格式（降级）
```python
{
    "original_ids": ["记忆ID1", "记忆ID2"],
    "original_texts": ["文本1", "文本2"],
    "refined_text": "文本1 | 文本2",
    "category": "reference",
    "refined": False
}
```

## 逻辑链与数据链

### 完整调用链
```
refine_group(memories)
  │
  ├─ 1. 提取原始数据
  │     └─ original_ids = [m["id"] for m in memories]
  │     └─ original_texts = [m["text"] for m in memories]
  │
  ├─ 2. 构建 prompt
  │     └─ _build_user_prompt(memories)
  │     └─ 格式化为 "请合并以下 N 条相似记忆：
[1] ...
[2] ..."
  │
  ├─ 3. 调用 LLM
  │     └─ call_llm(SYSTEM_PROMPT, user_prompt)
  │     │
  │     ├─ 3a. _load_llm_config()
  │     │     └─ load_mem0_config() → {llm_provider, llm_model, api_key, base_url}
  │     │
  │     ├─ 3b. 确定 base_url（空时按 provider 推断）
  │     │
  │     ├─ 3c. 创建 OpenAI 客户端
  │     │     └─ OpenAI(api_key=..., base_url=...)
  │     │
  │     └─ 3d. 调用 chat.completions.create
  │           └─ model, messages, temperature=0.3, max_tokens=1024, timeout=30
  │           └─ 返回 response.choices[0].message.content.strip()
  │
  ├─ 4. 解析响应
  │     └─ _parse_llm_response(raw)
  │     └─ 尝试直接JSON → 代码块 → 含refined_text的JSON → 降级
  │
  └─ 5. 构建结果（成功路径）
        └─ 返回 {"original_ids", "original_texts", "refined_text", "category", "refined": True}
```

### 降级路径
```
refine_group(memories)
  │
  └─ call_llm 抛出异常
     └─ logger.warning("[llm] 精炼失败，降级拼接: {e}")
     └─ fallback = " | ".join(original_texts)
     └─ 返回 {"original_ids", "original_texts", "refined_text": fallback, "category": "reference", "refined": False}
```

### 数据流转
```
memories: [{"id", "text"}, ...]
  ↓ 提取
original_ids: [str, ...], original_texts: [str, ...]
  ↓ _build_user_prompt
user_prompt: str
  ↓ call_llm → OpenAI API
raw: str (LLM原始响应)
  ↓ _parse_llm_response
result: {"refined_text", "category"}
  ↓ 组装
最终结果: {"original_ids", "original_texts", "refined_text", "category", "refined"}
```

## 错误处理与降级策略

### 1. LLM 调用失败
- **原因**：网络超时、API 错误、配额不足等
- **处理**：降级为简单文本拼接（`" | ".join(original_texts)`）
- **结果**：`refined=False`，category="reference"

### 2. JSON 解析失败
- **原因**：LLM 未按格式输出
- **处理**：尝试多种解析策略，最后使用原始文本
- **结果**：refined_text 为原始响应内容，category="reference"

### 3. 配置缺失
- **原因**：API Key 未配置
- **处理**：使用 "dummy" 作为占位 API Key
- **影响**：云端提供商调用会失败，本地模型可正常使用

## 使用场景

### 1. 与 dedup + organizer 模块协作
- dedup 模块找出相似组 → organizer 调用 refine_group 合并精炼 → 写回 mem0

## 注意事项

1. **API 成本**：频繁调用可能产生费用，需监控使用量
2. **数据隐私**：敏感信息避免发送到第三方服务
3. **模型差异**：不同模型表现可能差异较大
4. **提示词工程**：系统提示词对结果质量影响显著
5. **固定参数**：temperature=0.3、max_tokens=1024 为硬编码，不可配置
