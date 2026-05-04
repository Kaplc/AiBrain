# 后端-brain-dedup 模块

## 概述
`dedup.py` 是 AiBrain 大脑模块中的记忆去重组件，负责基于语义相似度的全量记忆去重分组。支持分批处理、实时 yield 组、暂停/恢复/停止控制。

## 核心功能

### 1. 同步全量去重（向后兼容）
- **范围**：处理用户的所有记忆
- **方法**：基于 Embedding 向量相似度
- **输出**：分组后的相似记忆集合

### 2. 流式去重（新增）
- **SSE 生成器**：`dedup_memories_iter()` 分批 yield 当前已发现的组
- **暂停/恢复/停止**：通过 threading.Event 全局标志控制
- **实时反馈**：每批处理完立即推送进度，适合大规模记忆

### 3. 自适应阈值
提供三个相似度阈值档位：
- **严格模式**：`THRESHOLD_STRICT = 0.90`（极高相似度）
- **中等模式**：`THRESHOLD_MEDIUM = 0.85`（默认，平衡精度和召回）
- **宽松模式**：`THRESHOLD_LOOSE = 0.80`（较高召回率）

## 算法原理

### 并查集聚类（通用）
用向量余弦相似度 + 并查集找出语义重复的记忆组

### 流式处理流程
1. 分批获取记忆向量（batch_size=30）
2. 批次内部两两比较 + 与历史编码比较
3. 实时更新并查集状态
4. 每批处理完 yield 当前已发现的组
5. 全量处理完后计算精确相似度并 final yield

## 主要函数

### `dedup_memories(threshold=THRESHOLD_MEDIUM)`
- **功能**：全量记忆去重分组的主函数（同步版本，保留向后兼容）
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

### `dedup_memories_iter(threshold, batch_size, pause_flag, stop_flag)`
- **功能**：流式去重生成器，分批处理记忆，发现新组时 yield
- **参数**：
  - `threshold`：相似度阈值，默认 0.85
  - `batch_size`：每批处理记忆数，默认 30
  - `pause_flag`：暂停事件（threading.Event），默认 `_dedup_pause_flag`
  - `stop_flag`：停止事件（threading.Event），默认 `_dedup_stop_flag`
- **Yields**：
  - `{"type": "batch", "found": N, "total": T, "groups": [...]}` 定期发送当前已发现组
  - `{"type": "done", "total": N, "grouped": M, "ungrouped": K, "groups": [...]}` 扫描完成
  - `{"type": "stopped", "found": N, "groups": [...]}` 中途停止
- **流式流程**：
  1. 分批获取文本并编码（batch_size=30）
  2. 批次内部两两比较 + 与历史已编码向量比较
  3. 实时更新 Union-Find 并查集
  4. 每批处理完调用 `_collect_groups()` 收集当前组，yield 进度
  5. 检测 pause_flag / stop_flag，实现暂停/停止
  6. 全量完成后计算精确相似度，yield 最终结果

### `_get_all_memories(client, user_id)`
- **功能**：从 mem0 获取指定用户的全部记忆
- **参数**：
  - `client`：mem0 客户端
  - `user_id`：用户ID
- **返回**：记忆列表，包含 id、text、timestamp
- **特点**：按 created_at 倒序排序，支持最多100,000条记忆

### `_union_find_cluster(sim_matrix, threshold)`
- **功能**：并查集聚类算法实现（用于同步版本）
- **参数**：
  - `sim_matrix`：相似度矩阵（n×n numpy数组）
  - `threshold`：相似度阈值
- **返回**：分组索引列表（每组至少2个元素）

### `_collect_groups(uf_parent, all_memories, all_vectors, all_indices, threshold)`
- **功能**：从 Union-Find 结构收集已确认的重复组（用于流式版本）
- **参数**：
  - `uf_parent`：并查集父节点数组
  - `all_memories`：全部记忆列表
  - `all_vectors`：已编码的向量列表
  - `all_indices`：向量对应的记忆索引
  - `threshold`：相似度阈值
- **返回**：分组列表（含精确计算的平均相似度）

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

### 同步版本输出分组格式
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

### 流式版本 SSE 消息格式
```python
# 定期发送当前已发现组（进度）
{"type": "batch", "found": 5, "total": 100, "groups": [...]}

# 分析完成
{"type": "done", "total": 100, "grouped": 30, "ungrouped": 70, "groups": [...]}

# 中途停止
{"type": "stopped", "found": 12, "groups": [...]}

# 异常
{"type": "error", "error": "错误信息"}
```

## 技术细节

### 1. 向量处理
- **编码模型**：BGE-M3（通过 `brain_mcp.embedding.encode_texts`）
- **批量编码**：流式版本分批编码（batch_size=30），同步版本一次性编码
- **归一化**：向量 L2 归一化（`norms = np.linalg.norm(mat, axis=1, keepdims=True)`），避免长度影响相似度计算
- **归一化下界**：使用 `np.maximum(norms, 1e-8)` 防止零向量除零
- **相似度计算**：`sim_matrix = mat @ mat.T`（矩阵乘法）

### 2. 并查集实现
- **路径压缩**：在 find 操作中压缩路径（`parent[x] = parent[parent[x]]`）
- **按秩合并**：流式版本使用 uf_rank 数组按秩合并，同步版本按索引顺序合并
- **效率**：O(n²) 相似度比较，适合中等规模数据

### 3. 流式处理（新增）
- **累积编码**：已编码向量累积在 `all_vectors`/`all_indices`，与新批次比较
- **跨批比较**：新批次向量与全部历史向量计算相似度，确保不遗漏跨批重复
- **状态持久化**：通过 threading.Event 全局标志 `_dedup_pause_flag` / `_dedup_stop_flag` 跨请求持久化控制状态

### 4. 暂停/恢复机制
```python
_dedup_pause_flag = threading.Event()  # 全局暂停标志
_dedup_stop_flag = threading.Event()  # 全局停止标志

# 暂停：_dedup_pause_flag.set()
# 恢复：_dedup_pause_flag.clear()
# 停止：_dedup_stop_flag.set()
```

## 逻辑链与数据链

### 同步版本调用链
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

### 流式版本调用链
```
dedup_memories_iter(threshold, batch_size, pause_flag, stop_flag)
  │
  ├─ 1. 获取 mem0 客户端和全部记忆
  │
  ├─ 2. 初始化 Union-Find（uf_parent, uf_rank）和累积向量列表
  │
  ├─ 3. 分批处理记忆（for batch_start in range(0, n, batch_size)）
  │     │
  │     ├─ 检测 stop_flag.is_set() → yield stopped，退出
  │     │
  │     ├─ 检测 pause_flag.is_set() → 循环 sleep 等待 clear 或 stop
  │     │
  │     ├─ 编码当前批次向量
  │     │
  │     ├─ 批次内部两两比较 → uf_union
  │     │
  │     ├─ 与历史已编码向量跨批比较 → uf_union
  │     │
  │     ├─ 累积向量到 all_vectors / all_indices
  │     │
  │     └─ yield batch 消息（当前已发现组）
  │
  ├─ 4. 全量完成后 _collect_groups 计算精确相似度
  │
  └─ 5. yield done 消息（最终结果）
```

### 数据流转（流式版本）
```
mem0 存储
  ↓ get_all(filters, top_k)
原始记忆列表 [{"id", "memory", "created_at"}, ...]
  ↓ 排序 + 字段映射
all_memories: [{"id", "text", "timestamp"}, ...]
  ↓ 分批提取文本
batch_texts: [str, ...]  (每批 batch_size 条)
  ↓ encode_texts()
batch_vecs: [[float, ...], ...]
  ↓ 与 all_vectors 跨批比较 + 并查集更新
  ↓ 累积到 all_vectors / all_indices
  ↓ _collect_groups() 收集当前组
  ↓ yield batch 消息
  ↓ ...重复直到全部处理完...
  ↓ _collect_groups() 最终精确相似度
最终分组列表 → yield done 消息
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

### 1. 记忆整理（同步版本）
- 定期运行去重，清理重复记忆
- 发现语义相似的记忆组

### 2. 记忆整理（流式版本，新增）
- 大规模记忆（>1000条）的实时进度反馈
- 支持暂停/恢复，适合长时间分析
- 前端 SSE 流式消费，实时显示已发现组

### 3. 与 organizer 模块协作
- dedup 找出相似组 → organizer 调用 llm 合并精炼 → 写回 mem0

## 注意事项

1. **语义相似度局限性**：基于向量的相似度可能无法捕捉逻辑关系
2. **阈值选择**：需要根据具体应用调整阈值
3. **计算资源**：大规模记忆需要较多计算资源
4. **依赖项**：依赖 `brain_mcp.embedding.encode_texts` 和 `modules.brain.mem0_adapter`
5. **流式版本线程安全**：全局 `_dedup_pause_flag` / `_dedup_stop_flag` 在多次请求间持久化，需要在每次新请求开始时重置
6. **SSE 连接断开**：客户端断开时请求端会通过 `_abortController.abort()` 中止生成器

---

*最后更新: 2026-05-04*
