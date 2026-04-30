# 后端-brain-migrate 模块

## 概述
`migrate.py` 是 AiBrain 大脑模块中的旧记忆迁移组件，负责从旧的 Qdrant `memories` 集合迁移数据到新的 `mem0_memories` 集合。该模块确保系统升级时的数据连续性，支持一次性迁移和防止重复执行。

## 核心功能

### 1. 数据迁移
- **源**：旧的 Qdrant `memories` 集合
- **目标**：新的 mem0 `mem0_memories` 集合
- **方式**：逐条读取、转换、存储

### 2. 迁移控制
- **防止重复**：通过迁移标记文件 `.mem0_migrated`
- **条件检查**：自动判断是否需要迁移
- **进度跟踪**：记录迁移统计信息

### 3. 数据过滤
- **空内容过滤**：跳过空白文本记录
- **已整理标记**：跳过包含 `[已整理]` 的记录
- **无效数据**：跳过无法处理的记录

## 迁移标记机制

### 迁移标记文件
- **文件名**：`.mem0_migrated`
- **位置**：项目根目录
- **作用**：防止重复执行迁移
- **内容**：简单的 "done" 文本

### 检查逻辑
```python
def needs_migration(project_root: str) -> bool:
    import os
    return not os.path.exists(os.path.join(project_root, _MIGRATION_FLAG))
```
- **存在标记**：不需要迁移
- **不存在标记**：需要迁移

## 主要函数

### `migrate_old_memories(project_root: str)`
- **功能**：从旧 Qdrant memories 集合读取所有记忆并迁移到 mem0
- **参数**：`project_root` - 项目根目录路径（用于标记文件）
- **返回**：迁移统计字典
- **工作流程**：
  1. 检查迁移标记
  2. 连接旧 Qdrant 服务
  3. 检查源集合是否存在和是否有数据
  4. 逐批读取旧记忆（每批100条）
  5. 过滤和处理每条记忆
  6. 存储到 mem0
  7. 写入迁移完成标记
  8. 返回迁移统计

### `needs_migration(project_root: str)`
- **功能**：检查是否需要迁移
- **参数**：项目根目录路径
- **返回**：布尔值，True 表示需要迁移
- **逻辑**：检查迁移标记文件是否存在

### `_write_flag(flag_path: str)`
- **功能**：写入迁移完成标记（内部函数）
- **参数**：标记文件路径
- **实现**：创建文件并写入 "done" 文本
- **错误处理**：静默失败，不影响主流程

## 迁移流程

### 1. 初始检查阶段
- 检查迁移标记文件
- 连接旧 Qdrant 服务
- 验证源集合 `memories` 是否存在
- 检查集合中是否有数据

### 2. 数据读取阶段
- 使用 `scroll` API 分页读取
- 每批100条记录
- 支持游标（offset）继续读取
- 读取完成后关闭游标

### 3. 数据处理阶段
对每条记录执行：
1. **提取文本**：从 payload 获取 text 字段
2. **内容验证**：
   - 检查文本是否为空或仅空白
   - 检查是否包含 `[已整理]` 标记（跳过已整理记录）
3. **迁移存储**：
   - 使用 `infer=False` 直接存储，避免 LLM 重新推理
   - 用户ID设为 "default"
   - 捕获并处理存储异常

### 4. 完成阶段
- 写入迁移标记文件
- 记录迁移统计日志
- 返回迁移结果

## 数据结构

### 源数据格式（旧 Qdrant）
```python
{
    "id": "记录ID",
    "payload": {
        "text": "记忆内容文本",
        "user_id": "用户ID",
        "created_at": "创建时间",
        "metadata": {}  # 附加元数据
    },
    "vector": [...]  # 向量数据（可选）
}
```

### 迁移统计结果
```python
{
    "migrated": 45,      # 成功迁移的记录数
    "skipped": 5,        # 跳过的记录数
    "error": None        # 错误信息（成功时为 None）
}
```

## 技术细节

### 1. Qdrant 连接配置
```python
old_client = QdrantClient(
    host=brain_settings.qdrant_host,      # 通常 "localhost"
    grpc_port=brain_settings.grpc_port,   # 通常 6334
    prefer_grpc=True,                     # 优先使用 gRPC
    check_compatibility=False,            # 不检查兼容性
)
```

### 2. 分页读取策略
```python
results, offset = old_client.scroll(
    collection_name=brain_settings.collection_name,  # 通常是 "memories"
    offset=offset,                                   # 游标，None 表示开始
    limit=100,                                       # 每批大小
)
```

### 3. 存储配置
```python
# 使用 infer=False 直接存储，避免 LLM 重新推理
mem0_client.add(
    text,                    # 记忆文本
    user_id="default",       # 默认用户ID
    infer=False,             # 不调用 LLM 推理
)
```

## 错误处理

### 1. 连接失败
- **场景**：旧 Qdrant 服务不可用
- **处理**：返回错误信息，迁移计数为0
- **返回**：`{"migrated": 0, "skipped": 0, "error": "错误信息"}`

### 2. 集合不存在
- **场景**：源集合 `memories` 不存在
- **处理**：记录日志，返回成功（无数据迁移）
- **返回**：`{"migrated": 0, "skipped": 0, "error": None}`

### 3. 空集合
- **场景**：源集合存在但没有数据
- **处理**：记录日志，返回成功
- **返回**：`{"migrated": 0, "skipped": 0, "error": None}`

### 4. 单条记录失败
- **场景**：某条记录存储失败
- **处理**：记录警告日志，计入 skipped 计数
- **继续**：继续处理后续记录

### 5. 标记文件写入失败
- **场景**：无法创建标记文件
- **处理**：静默失败，不影响主流程
- **影响**：可能导致重复迁移尝试

## 性能考虑

### 1. 批量处理
- **批大小**：100条/批
- **优势**：平衡内存使用和网络开销
- **调整建议**：根据数据量调整批大小

### 2. 网络连接
- **gRPC 优先**：使用 gRPC 协议提高传输效率
- **连接复用**：保持 Qdrant 连接
- **超时处理**：依赖底层库的超时机制

### 3. 内存使用
- **流式处理**：分批读取，避免一次性加载所有数据
- **及时释放**：处理完一批后及时释放资源
- **进度跟踪**：可添加进度报告功能

## 使用场景

### 1. 系统升级
- 从旧版 AiBrain 升级到新版
- 迁移历史记忆数据
- 保持用户数据连续性

### 2. 数据迁移
- 更换向量数据库后端
- 调整数据存储结构
- 数据清理和重整

### 3. 测试验证
- 验证迁移流程
- 测试数据兼容性
- 性能基准测试

## 集成方式

### 1. 启动时自动迁移
```python
# 在应用启动时检查并执行迁移
if needs_migration(project_root):
    result = migrate_old_memories(project_root)
    if result["error"]:
        logger.error(f"迁移失败: {result['error']}")
    else:
        logger.info(f"迁移完成: {result['migrated']} 条已迁移, {result['skipped']} 条跳过")
```

### 2. 手动触发迁移
```python
# 提供 API 端点手动触发迁移
@app.route('/migrate', methods=['POST'])
def api_migrate():
    if not needs_migration(project_root):
        return jsonify({"status": "already_migrated"})
    
    result = migrate_old_memories(project_root)
    return jsonify(result)
```

### 3. 命令行工具
```python
# 可作为独立脚本运行
if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = migrate_old_memories(project_root)
    print(json.dumps(result, indent=2))
```

## 配置依赖

### 1. Qdrant 设置
从 `brain_mcp.config.settings` 获取：
- `qdrant_host`：Qdrant 主机地址
- `grpc_port`：gRPC 端口号
- `collection_name`：源集合名称（通常是 "memories"）

### 2. mem0 客户端
通过 `get_mem0_client()` 获取：
- 使用 mem0_adapter 模块的客户端
- 已配置好目标集合 `mem0_memories`
- 支持正确的 Embedding 模型和向量维度

## 扩展功能

### 1. 增量迁移
- 只迁移新增或修改的记录
- 基于时间戳过滤
- 支持断点续传

### 2. 数据转换
- 更复杂的数据清洗
- 格式转换和规范化
- 质量检查和修复

### 3. 进度报告
- 实时进度显示
- 预估剩余时间
- 详细日志输出

### 4. 回滚机制
- 迁移失败时回滚
- 数据一致性保证
- 备份和恢复

### 5. 多版本支持
- 支持多个旧版本数据格式
- 自动检测版本并应用相应迁移逻辑
- 版本升级路径管理

## 监控与日志

### 1. 运行日志
```log
[migrate] Migrating 150 memories from 'memories'...
[migrate] Migration complete: migrated=145, skipped=5
[migrate] Failed to migrate memory abc123: Connection timeout
```

### 2. 性能指标
- 迁移总时间
- 迁移速率（条/秒）
- 成功率和失败率

### 3. 数据质量
- 迁移前后数据对比
- 内容完整性检查
- 向量相似度验证

## 安全考虑

### 1. 数据完整性
- 确保迁移过程不丢失数据
- 验证迁移后的数据可访问
- 提供数据校验机制

### 2. 权限控制
- 验证对源集合的读取权限
- 验证对目标集合的写入权限
- 记录迁移操作日志

### 3. 敏感数据处理
- 避免在日志中记录敏感信息
- 安全存储迁移标记文件
- 清理临时数据

## 故障排查

### 1. 常见问题
- **连接失败**：检查 Qdrant 服务状态
- **权限不足**：验证数据库访问权限
- **数据格式不匹配**：检查源数据格式
- **内存不足**：减少批处理大小

### 2. 调试方法
1. 检查迁移标记文件是否存在
2. 验证 Qdrant 服务连接
3. 检查源集合是否存在和包含数据
4. 测试单条记录迁移
5. 查看详细错误日志

### 3. 恢复步骤
1. 删除迁移标记文件（如果需要重新迁移）
2. 清理部分迁移的数据（如果迁移中断）
3. 检查并修复数据一致性问题
4. 重新执行迁移

## 注意事项

1. **一次性操作**：迁移设计为一次性执行，重复执行可能造成数据重复
2. **数据一致性**：迁移期间应避免对源数据的修改
3. **资源需求**：大规模迁移可能需要较多时间和资源
4. **备份建议**：迁移前建议备份源数据
5. **测试验证**：生产环境迁移前应在测试环境验证
6. **监控告警**：迁移过程中应监控系统状态和资源使用