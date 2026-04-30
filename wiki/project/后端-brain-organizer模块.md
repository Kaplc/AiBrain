# 后端-brain-organizer 模块

## 概述
`organizer.py` 是 AiBrain 大脑模块中的记忆整理组件，负责按类型分类并结构化记忆。该模块从 `brain_mcp/_organizer.py` 迁移而来，提供记忆分类、结构化生成和整理摘要功能，帮助用户系统化管理和组织记忆。

## 核心功能

### 1. 记忆分类
- **自动分类**：将记忆分配到5个预定义类别
- **向量相似度**：基于记忆内容与类别描述的语义相似度
- **批量处理**：支持同时分类多条记忆

### 2. 结构化生成
- **个体结构化**：为每条记忆添加类别标签
- **整理文本生成**：生成格式化的整理报告
- **摘要生成**：创建分类统计和内容预览

### 3. 整理流程
- **一体化处理**：输入查询和相关记忆，输出完整整理结果
- **ID 管理**：跟踪原始记忆ID，支持后续操作
- **结果丰富**：提供多层次整理信息

## 记忆类型体系

### TYPE_DESCRIPTIONS 字典
```python
TYPE_DESCRIPTIONS = {
    "user": "用户个人信息、偏好、习惯、感受",
    "feedback": "用户反馈、建议、意见、改进想法",
    "project": "项目开发、代码、功能实现、技术任务",
    "reference": "文档、链接、参考资料、学习笔记",
    "ai": "AI 自身的行为、偏好、记忆、经验总结"
}
```

### 类型说明
1. **user（用户）**
   - 用户个人信息、偏好、习惯、感受
   - 示例：用户喜欢喝咖啡、用户习惯早起

2. **feedback（反馈）**
   - 用户反馈、建议、意见、改进想法
   - 示例：用户希望增加导出功能、用户报告了一个bug

3. **project（项目）**
   - 项目开发、代码、功能实现、技术任务
   - 示例：实现登录功能、修复数据库连接问题

4. **reference（参考）**
   - 文档、链接、参考资料、学习笔记
   - 示例：React文档链接、机器学习算法笔记

5. **ai（AI）**
   - AI 自身的行为、偏好、记忆、经验总结
   - 示例：AI学会了如何解释代码、AI偏好简洁的回答

## 主要函数

### `organize_memories(query, related_memories)`
- **功能**：整理记忆的主函数，一体化处理流程
- **参数**：
  - `query`：整理查询主题
  - `related_memories`：相关记忆列表
- **返回**：完整的整理结果字典
- **工作流程**：
  1. 输入验证（空记忆处理）
  2. 记忆分类（`classify_memories`）
  3. 生成摘要（`generate_summary`）
  4. 生成整理文本（`generate_organized_text`）
  5. 生成个体结构化记忆（`generate_individual_structured_memories`）
  6. 构建返回结果

### `classify_memories(memories)`
- **功能**：将记忆按类型分类
- **参数**：记忆列表
- **返回**：按类型分组的字典
- **算法**：
  1. 批量编码记忆文本向量
  2. 批量编码类型描述向量
  3. 对每条记忆，计算与每个类型描述的余弦相似度
  4. 选择相似度最高的类型作为分类结果
  5. 返回分类后的字典

### `generate_individual_structured_memories(categorized)`
- **功能**：为分类后的记忆生成个体结构化版本
- **参数**：分类后的记忆字典
- **返回**：结构化记忆列表
- **处理**：
  1. 遍历每个类型和其中的记忆
  2. 清理记忆文本（移除已有的类型标签）
  3. 添加新的类型标签前缀 `[{type_name}]`
  4. 保留原始ID和添加分类信息

### `generate_organized_text(query, categorized)`
- **功能**：生成格式化的整理报告文本
- **参数**：
  - `query`：整理主题
  - `categorized`：分类后的记忆字典
- **返回**：Markdown格式的整理文本
- **格式**：
  ```
  # 记忆整理 - 主题: {query}
  ## 整理时间: {timestamp}
  
  ### USER (N条)
  - 记忆内容1
  - 记忆内容2
  
  ### FEEDBACK (N条)
  - 记忆内容3
  ...
  ```

### `generate_summary(categorized)`
- **功能**：生成整理摘要，包含统计和预览
- **参数**：分类后的记忆字典
- **返回**：摘要信息列表
- **内容**：
  - 每个类型的记忆数量
  - 每个类型的前几条记忆预览（截断）
  - 便于快速浏览整理概况

## 数据结构

### 输入记忆格式
```python
[
    {
        "id": "记忆ID",
        "text": "记忆内容文本",
        # 可包含其他字段如 timestamp, metadata 等
    },
    # ... 更多记忆
]
```

### 分类结果格式
```python
{
    "user": [
        {"id": "id1", "text": "用户喜欢喝咖啡"},
        {"id": "id2", "text": "用户习惯早起"}
    ],
    "feedback": [
        {"id": "id3", "text": "希望增加导出功能"}
    ],
    "project": [],
    "reference": [
        {"id": "id4", "text": "React文档链接"}
    ],
    "ai": []
}
```

### 整理结果格式
```python
{
    "query": "用户偏好",                     # 原始查询
    "total_found": 4,                       # 找到的记忆总数
    "categories": { ... },                  # 分类结果（同上）
    "organized": [                          # 整理摘要
        {
            "category": "user",
            "count": 2,
            "summary": "用户喜欢喝咖啡 | 用户习惯早起"
        },
        {
            "category": "feedback", 
            "count": 1,
            "summary": "希望增加导出功能"
        },
        # ... 其他类型
    ],
    "deleted_ids": ["id1", "id2", "id3", "id4"],  # 原始记忆ID（用于删除）
    "organized_text": "# 记忆整理 - 主题: 用户偏好\n...",  # 完整整理文本
    "individual_memories": [                # 个体结构化记忆
        {
            "id": "id1",
            "text": "[user] 用户喜欢喝咖啡",
            "category": "user"
        },
        # ... 其他结构化记忆
    ]
}
```

## 技术实现

### 1. 向量编码
- **编码函数**：`brain_mcp.embedding.encode_texts`
- **批量处理**：一次性编码所有记忆文本和类型描述
- **模型**：BGE-M3 或配置的 Embedding 模型
- **输出**：归一化的向量表示

### 2. 相似度计算
```python
# 计算余弦相似度（简化版，实际使用矩阵运算）
score = sum(a * b for a, b in zip(text_vec, type_vec))
```
- **原理**：向量点积（已归一化，等价于余弦相似度）
- **批量优化**：实际使用矩阵乘法提高效率
- **范围**：相似度值范围 [-1, 1]，实际在 [0, 1] 之间

### 3. 文本清理
```python
cleaned_text = re.sub(r"^\s*\[[a-zA-Z]+\]\s*", "", original_text).strip()
```
- **目的**：移除记忆文本中可能已存在的类型标签
- **模式**：匹配开头的 `[类型]` 标签（忽略空格）
- **示例**：`"[user] 喜欢咖啡"` → `"喜欢咖啡"`

### 4. 时间戳生成
```python
from datetime import datetime
timestamp = datetime.now().isoformat()
```
- **格式**：ISO 8601 格式
- **用途**：记录整理操作的时间
- **位置**：整理文本的标题部分

## 使用场景

### 1. 记忆整理界面
- 用户输入查询主题
- 系统检索相关记忆
- 自动分类和生成整理报告
- 提供结构化记忆供进一步处理

### 2. 定期记忆维护
- 定时运行整理功能
- 清理和重组记忆库
- 生成维护报告

### 3. 知识发现
- 分析记忆类型分布
- 发现知识盲点或重复
- 优化记忆存储策略

### 4. 导出和分享
- 生成可读的整理报告
- 导出结构化数据
- 分享知识整理成果

## 集成示例

### 1. 与搜索功能集成
```python
from modules.brain.memory import search_memories
from modules.brain.organizer import organize_memories

# 搜索相关记忆
search_results = search_memories("用户偏好", limit=50)

# 整理记忆
organized = organize_memories("用户偏好", search_results)

# 使用整理结果
print(f"找到 {organized['total_found']} 条相关记忆")
for category_summary in organized['organized']:
    print(f"{category_summary['category']}: {category_summary['count']} 条")
```

### 2. API 端点示例
```python
@app.route('/organize', methods=['POST'])
def api_organize():
    data = request.json
    query = data.get('query', '')
    memories = data.get('memories', [])
    
    if not query or not memories:
        return jsonify({"error": "query and memories are required"}), 400
    
    try:
        result = organize_memories(query, memories)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 3. 批量处理示例
```python
# 分批处理大量记忆
def batch_organize(all_memories, batch_size=100):
    all_results = []
    for i in range(0, len(all_memories), batch_size):
        batch = all_memories[i:i+batch_size]
        result = organize_memories("综合整理", batch)
        all_results.append(result)
    return merge_organize_results(all_results)
```

## 性能优化

### 1. 批量编码
- 一次性编码所有记忆文本
- 一次性编码所有类型描述
- 减少 Embedding 模型调用次数

### 2. 矩阵运算
- 使用 numpy 或 torch 进行矩阵乘法
- 避免循环计算相似度
- 提高大规模数据处理效率

### 3. 内存管理
- 分批处理大规模记忆
- 及时释放临时变量
- 使用生成器处理流式数据

### 4. 缓存策略
- 缓存类型描述向量（不变）
- 缓存常见记忆的向量表示
- 增量更新缓存

## 扩展功能

### 1. 自定义类型体系
- 支持用户定义类型和描述
- 动态加载类型配置
- 类型体系学习和优化

### 2. 多级分类
- 主类别和子类别
- 层次化分类体系
- 更精细的记忆组织

### 3. 质量评估
- 分类准确率评估
- 整理结果质量评分
- 用户反馈学习

### 4. 自动化整理
- 定时自动整理
- 基于事件触发整理
- 智能整理建议

### 5. 可视化输出
- 生成图表和可视化
- 交互式整理界面
- 多维数据展示

## 错误处理

### 1. 空输入处理
```python
if not memories:
    return {t: [] for t in TYPE_DESCRIPTIONS}
```
- 空记忆列表返回空分类结果
- 避免后续计算错误

### 2. 编码失败
- 单个记忆编码失败跳过
- 记录错误日志
- 返回部分结果

### 3. 内存不足
- 检测内存使用量
- 自动切换到分批处理
- 提供进度反馈

### 4. 参数验证
- 验证输入格式
- 检查必需字段
- 提供明确错误信息

## 监控与日志

### 1. 运行日志
```log
[organizer] 分类 150 条记忆
[organizer] 生成整理报告，主题: 用户偏好
[organizer] 整理完成: 5 个类别，45 条记忆已分类
```

### 2. 性能指标
- 分类处理时间
- 记忆数量分布
- 类型分布统计

### 3. 质量指标
- 分类置信度
- 整理完整性
- 用户满意度

## 注意事项

1. **类型描述质量**：类型描述的准确性直接影响分类效果
2. **语言支持**：依赖 Embedding 模型的多语言能力
3. **领域适应性**：通用分类可能不适用于专业领域
4. **记忆质量**：低质量记忆可能影响分类准确性
5. **实时性需求**：大规模记忆整理可能需要较长时间
6. **结果可解释性**：提供分类依据和置信度信息