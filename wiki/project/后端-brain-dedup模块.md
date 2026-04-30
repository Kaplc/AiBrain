# 后端-brain-dedup 模块

## 概述
`dedup.py` 是 AiBrain 大脑模块中的记忆去重组件，负责基于语义相似度的全量记忆去重分组。该模块使用向量余弦相似度和并查集算法，自动识别和分组语义重复的记忆，帮助用户整理和优化记忆库。

## 核心功能

### 1. 全量记忆去重
- **范围**：处理用户的所有记忆
- **方法**：基于 Embedding 向量相似度
- **输出**：分组后的相似记忆集合

### 2. 自适应阈值
提供三个相似度阈值档位：
- **严格模式**：`THRESHOLD_STRICT = 0.90`（极高相似度）
- **中等模式**：`THRESHOLD_MEDIUM = 0.85`（默认，平衡精度和召回）
- **宽松模式**：`THRESHOLD_LOOSE = 0.80`（较高召回率）

## 算法原理

### 两步去重法（第一步）
用向量余弦相似度 + 并查集找出语义重复的记忆组

### 技术流程
1. **数据获取**：从 mem0 获取用户全部记忆
2. **向量编码**：使用 BGE-M3 模型编码记忆文本
3. **相似度计算**：计算记忆间的余弦相似度矩阵
4. **聚类分组**：使用并查集算法基于阈值聚类
5. **结果整理**：计算组内平均相似度，排序输出

## 主要函数

### `dedup_memories(threshold=THRESHOLD_MEDIUM)`
- **功能**：全量记忆去重分组的主函数
- **参数**：
  - `threshold`：余弦相似度阈值，默认 0.85
- **返回**：包含分组结果的字典
- **工作流程**：
  1. 获取 mem0 客户端和默认用户ID
  2. 读取用户全部记忆（按创建时间倒序）
  3. 批量编码记忆文本为向量
  4. 向量归一化并计算相似度矩阵
  5. 并查集聚类找出相似组
  6. 构建分组结果，计算统计信息

### `_get_all_memories(client, user_id)`
- **功能**：从 mem0 获取指定用户的全部记忆
- **参数**：
  - `client`：mem0 客户端
  - `user_id`：用户ID
- **返回**：记忆列表，包含 id、text、timestamp
- **特点**：按 created_at 倒序排序，支持最多100,000条记忆

### `_union_find_cluster(sim_matrix, threshold)`
- **功能**：并查集聚类算法实现
- **参数**：
  - `sim_matrix`：相似度矩阵（n×n numpy数组）
  - `threshold`：相似度阈值
- **返回**：分组索引列表（每组至少2个元素）
- **算法**：
  1. 初始化并查集父节点数组
  2. 遍历所有记忆对 (i, j)
  3. 如果相似度 ≥ 阈值，合并两个记忆
  4. 收集所有分组（排除单元素组）

## 数据结构

### 输入记忆格式
```python
[
    {
        "id": "记忆ID",
        "text": "记忆内容",
        "timestamp": "创建时间"
    },
    # ... 更多记忆
]
```

### 输出分组格式
```python
{
    "groups": [
        {
            "group_id": 0,
            "memories": [
                {
                    "id": "记忆ID1",
                    "text": "记忆内容1",
                    "timestamp": "时间戳1"
                },
                {
                    "id": "记忆ID2", 
                    "text": "记忆内容2",
                    "timestamp": "时间戳2"
                }
            ],
            "similarity": 0.9123  # 组内平均相似度
        },
        # ... 更多分组
    ],
    "total_memories": 150,      # 总记忆数
    "grouped_count": 45,        # 参与分组的记忆数
    "ungrouped_count": 105      # 独立记忆数
}
```

## 技术细节

### 1. 向量处理
- **编码模型**：BGE-M3（通过 `brain_mcp.embedding.encode_texts`）
- **批量编码**：一次性编码所有记忆文本
- **归一化**：向量 L2 归一化（`norms = np.linalg.norm(mat, axis=1, keepdims=True)`），避免长度影响相似度计算
- **归一化下界**：使用 `np.maximum(norms, 1e-8)` 防止零向量除零
- **相似度计算**：`sim_matrix = mat @ mat.T`（矩阵乘法）

### 2. 并查集实现
- **路径压缩**：在 find 操作中压缩路径（`parent[x] = parent[parent[x]]`）
- **合并策略**：按索引顺序合并（`parent[ra] = rb`），非按秩合并
- **效率**：O(n²) 相似度比较，适合中等规模数据

### 3. 相似度矩阵
- **对称矩阵**：只计算上三角部分（`for i in range(n): for j in range(i+1, n)`）
- **内存优化**：使用 numpy 数组高效存储

### 4. 分组结果处理
- 组内平均相似度：计算组内所有两两对的相似度均值
- 按相似度降序排列后重新编号 group_id

## 逻辑链与数据链

### 完整调用链
```
dedup_memories(threshold)
  │
  ├─ 1. 获取 mem0 客户端
  │     └─ from modules.brain.mem0_adapter import get_mem0_client
  │     └─ from modules.brain.memory import DEFAULT_USER_ID
  │
  ├─ 2. _get_all_memories(client, DEFAULT_USER_ID)
  │     └─ client.get_all(filters={"user_id": user_id}, top_k=100000)
  │     └─ 提取 id/memory/created_at → [{"id", "text", "timestamp"}, ...]
  │     └─ 按 created_at 倒序排序
  │
  ├─ 3. 空记忆检查 → 返回空结果
  │
  ├─ 4. 批量编码
  │     └─ texts = [m["text"] for m in all_memories]
  │     └─ vectors = encode_texts(texts)   # brain_mcp.embedding
  │
  ├─ 5. 向量归一化
  │     └─ mat = np.array(vectors, dtype=np.float32)
  │     └─ norms = np.linalg.norm(mat, axis=1, keepdims=True)
  │     └─ mat = mat / np.maximum(norms, 1e-8)
  │
  ├─ 6. 相似度矩阵
  │     └─ sim_matrix = mat @ mat.T
  │
  ├─ 7. 并查集聚类
  │     └─ _union_find_cluster(sim_matrix, threshold)
  │     └─ 返回 [[idx1, idx2, ...], ...] 每组≥2个元素
  │
  └─ 8. 构建结果
        └─ 遍历 cluster_indices，收集 grouped_indices
        └─ 计算组内平均相似度
        └─ 按相似度降序排列，重新编号
        └─ 返回 {"groups", "total_memories", "grouped_count", "ungrouped_count"}
```

### 数据流转
```
mem0 存储
  ↓ get_all(filters, top_k)
原始记忆列表 [{"id", "memory", "created_at"}, ...]
  ↓ 排序 + 字段映射
_all_memories: [{"id", "text", "timestamp"}, ...]
  ↓ 提取文本
texts: [str, ...]
  ↓ encode_texts()
vectors: [[float, ...], ...]
  ↓ numpy + 归一化
mat: np.ndarray (n × dim)
  ↓ mat @ mat.T
sim_matrix: np.ndarray (n × n)
  ↓ 并查集聚类
cluster_indices: [[int, ...], ...]
  ↓ 构建分组 + 排序
返回结果 dict
```

## 错误处理

### 1. 空记忆处理
- 记忆列表为空时直接返回 `{"groups": [], "total_memories": 0, "grouped_count": 0, "ungrouped_count": 0}`
- 避免不必要的计算

### 2. 向量编码
- 依赖 `brain_mcp.embedding.encode_texts` 的错误处理
- 编码失败会抛出异常，由调用方处理

## 性能考虑

### 1. 时间复杂度
- **向量编码**：O(n)，取决于模型和文本长度
- **相似度计算**：O(n²)，主要瓶颈
- **聚类算法**：O(n² × α(n))，α 为反阿克曼函数，近似常数

### 2. 内存使用
- **向量存储**：n × embedding_dim（通常 1024 维）× 4 bytes
- **相似度矩阵**：n × n × 4 bytes
- 10000 条记忆约需 400MB 相似度矩阵

## 使用场景

### 1. 记忆整理
- 定期运行去重，清理重复记忆
- 发现语义相似的记忆组

### 2. 与 organizer 模块协作
- dedup 找出相似组 → organizer 调用 llm 合并精炼 → 写回 mem0

## 注意事项

1. **语义相似度局限性**：基于向量的相似度可能无法捕捉逻辑关系
2. **阈值选择**：需要根据具体应用调整阈值
3. **计算资源**：大规模记忆需要较多计算资源
4. **依赖项**：依赖 `brain_mcp.embedding.encode_texts` 和 `modules.brain.mem0_adapter`
