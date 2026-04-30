# 后端 - Status 模块

## 概述
Status 模块是 AiBrain 系统的状态监控模块，负责提供系统运行状态、硬件信息、数据库状态和模型信息。该模块通过多个 API 端点实时反馈系统的健康状态和资源配置。

## 主要功能

### 1. 系统状态监控
- **模型加载状态**：检查 embedding 模型是否成功加载
- **Qdrant 向量数据库状态**：检查向量数据库连接和集合状态
- **GPU/CUDA 可用性**：检测系统 GPU 硬件和 CUDA 支持情况
- **设备信息**：显示当前使用的计算设备（CPU/GPU）

### 2. 硬件信息收集
- **CPU 使用率**：实时 CPU 占用百分比
- **内存信息**：总内存、已用内存、内存使用率
- **GPU 信息**：NVIDIA GPU 名称、显存使用、温度监控
- **系统信息**：操作系统版本、Python 版本、平台信息

### 3. 数据库状态检查
- **Qdrant 存储统计**：向量集合中的记忆数量、存储空间大小
- **数据库连接状态**：SQLite 统计数据库的连接状态

### 4. 模型信息查询
- **本地模型检查**：检查 HuggingFace 模型是否已下载到本地
- **模型参数统计**：embedding 模型的参数数量、维度信息
- **缓存状态**：HuggingFace 缓存中的模型可用性

## API 接口

### GET `/status`
**功能**：获取系统核心状态信息

**响应示例**：
```json
{
  "model_loaded": true,
  "qdrant_ready": true,
  "device": "cuda",
  "cuda_available": true,
  "gpu_hardware": true,
  "gpu_name": "NVIDIA GeForce RTX 4090",
  "embedding_model": "bge-m3",
  "embedding_dim": 1024,
  "model_size": "568M",
  "qdrant_host": "127.0.0.1",
  "qdrant_port": 6333,
  "qdrant_collection": "mem0_memories",
  "qdrant_top_k": 50,
  "qdrant_disk_size": 157286400,
  "qdrant_storage_path": "qdrant/storage"
}
```

**字段说明**：
- `model_loaded`：embedding 模型是否加载成功
- `qdrant_ready`：Qdrant 向量数据库是否就绪
- `device`：当前使用的计算设备（cpu/cuda）
- `cuda_available`：PyTorch CUDA 是否可用
- `gpu_hardware`：系统是否有 NVIDIA GPU 硬件
- `gpu_name`：GPU 设备名称
- `embedding_model`：使用的 embedding 模型名称
- `embedding_dim`：向量维度
- `model_size`：模型参数量（B/M/K）
- `qdrant_host`：Qdrant 主机地址
- `qdrant_port`：Qdrant 端口
- `qdrant_collection`：向量集合名称
- `qdrant_top_k`：默认返回的相似度结果数量
- `qdrant_disk_size`：Qdrant 存储目录大小（字节）
- `qdrant_storage_path`：Qdrant 存储路径（相对路径）

### GET `/system-info`
**功能**：获取详细的系统硬件信息

**响应示例**：
```json
{
  "cpu_percent": 12.5,
  "memory_total": 34359738368,
  "memory_used": 12884901888,
  "memory_percent": 37.5,
  "platform": "Windows-10-10.0.19045-SP0",
  "os_name": "Windows",
  "os_version": "10.0.19045",
  "python_version": "3.12.0",
  "gpu": {
    "name": "NVIDIA GeForce RTX 4090",
    "memory_total": 25769803776,
    "memory_used": 1073741824,
    "memory_free": 24696061952,
    "memory_percent": 4,
    "temperature": 45
  }
}
```

**字段说明**：
- `cpu_percent`：CPU 使用百分比
- `memory_total`：总物理内存（字节）
- `memory_used`：已用内存（字节）
- `memory_percent`：内存使用百分比
- `platform`：完整平台信息
- `os_name`：操作系统名称
- `os_version`：操作系统版本
- `python_version`：Python 版本
- `gpu`：GPU 信息对象（如无 GPU 则为 null）

### GET `/db-status`
**功能**：检查统计数据库状态

**响应示例**：
```json
{
  "ok": true,
  "daily_stats_count": 150,
  "stream_count": 2500,
  "search_history_count": 120
}
```

### GET `/memory-count`
**功能**：获取记忆总数（从统计数据库读取，数据库已与 Qdrant 同步）

**响应示例**：
```json
{
  "count": 1250
}
```

### GET `/model-info`
**功能**：检查本地模型文件状态

**响应示例**：
```json
{
  "local_models_dir": "C:/Users/user/Desktop/AiBrain/models",
  "model_name": "BAAI/bge-m3",
  "local_path": "C:/Users/user/Desktop/AiBrain/models/BAAI_bge-m3",
  "local_available": true,
  "hf_cache_available": true,
  "embedding_dim": 1024
}
```

## 技术实现

### 核心函数

#### `_get_qdrant_count(settings)`
**功能**：查询 Qdrant 集合中的记忆数量和存储大小

**实现逻辑**：
1. 连接 Qdrant 客户端
2. 获取集合信息，提取 `points_count`
3. 递归遍历 Qdrant 存储目录计算磁盘使用量
4. 返回包含数量、磁盘大小和存储路径的字典

#### `_get_qdrant_count_cached(settings, logger)`
**功能**：缓存 Qdrant 计数，启动时查询一次，后续直接使用缓存

**优化策略**：
- 使用模块级变量 `_qdrant_cache` 存储查询结果
- 启动时只查询一次，避免频繁访问 Qdrant 影响性能
- 日志记录缓存初始化过程

#### `_get_model_info()`
**功能**：获取 embedding 模型信息

**实现逻辑**：
1. 从 embedding 模块获取模型名称
2. 提取模型简称（去除路径部分）
3. 计算模型参数量并格式化显示
4. 返回名称和大小信息

#### `_has_nvidia_gpu()`
**功能**：检测系统是否有 NVIDIA GPU 硬件（不依赖 CUDA 版 PyTorch）

**检测策略**：
1. 优先使用 pynvml 库检测 NVIDIA 设备
2. 回退方案：使用 Windows WMIC 命令查询显卡信息
3. 通过名称中是否包含 "nvidia" 判断

### 依赖库
- **psutil**：系统资源监控（CPU、内存）
- **torch**：GPU/CUDA 检测
- **pynvml**：NVIDIA GPU 信息查询（可选）
- **qdrant_client**：Qdrant 向量数据库客户端
- **huggingface_hub**：模型缓存检查

## 配置管理

### 环境变量
- `QDRANT_EMBEDDING_DIM`：向量维度（默认 1024）
- `QDRANT_HOST`：Qdrant 主机地址（默认 127.0.0.1）
- `QDRANT_PORT`：Qdrant 端口（默认 6333）

### 缓存策略
- **Qdrant 计数缓存**：应用启动时查询一次，后续所有请求使用缓存值
- **GPU 检测缓存**：每次请求实时检测，确保信息准确
- **模型信息缓存**：每次请求重新计算，确保反映最新状态

## 错误处理

### 优雅降级
1. **Qdrant 连接失败**：返回 count=0，disk_size=0，不影响其他功能
2. **GPU 信息获取失败**：返回 gpu=null，继续提供其他系统信息
3. **模型参数计算失败**：返回空字符串的 size 字段

### 日志记录
- 关键操作记录 INFO 级别日志
- 错误情况记录 WARNING 或 ERROR 级别日志
- 缓存初始化过程详细记录

## 使用场景

### 系统监控面板
- Overview 模块调用 `/status` 显示系统概览
- 实时监控系统资源使用情况
- 快速诊断模型和数据库状态

### 故障排查
- 通过状态信息定位问题根源
- 检查 GPU 是否正常识别
- 验证模型文件是否正确加载

### 资源规划
- 根据记忆数量评估存储需求
- 监控内存和 GPU 使用情况
- 规划系统扩容时机

## 性能考虑

### 优化措施
1. **缓存机制**：Qdrant 计数只查询一次，避免频繁网络请求
2. **并行检测**：CPU、内存、GPU 信息并行收集
3. **超时控制**：外部命令执行设置超时，避免阻塞
4. **懒加载**：pynvml 等可选库按需导入

### 资源消耗
- CPU 使用率检测间隔 0.1 秒，平衡准确性和性能
- 内存信息直接从系统 API 获取，开销小
- GPU 温度检测仅在 CUDA 可用时执行

## 相关模块

### 前端模块
- **Overview 模块**：主要消费者，显示状态信息
- **Settings 模块**：设备配置和模型重载

### 后端模块
- **Memory 模块**：依赖 Qdrant 状态
- **Stats 模块**：提供数据库状态信息
- **Settings_mod 模块**：设备设置管理

## 扩展计划

### 短期改进
1. **更多硬件指标**：磁盘使用率、网络状态
2. **服务健康检查**：MCP 服务器状态监控
3. **历史趋势**：状态变化历史记录

### 长期规划
1. **预警机制**：资源使用超过阈值时发送通知
2. **自动化修复**：检测到问题后自动尝试修复
3. **集群监控**：支持多节点状态监控