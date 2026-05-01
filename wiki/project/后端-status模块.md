# 后端 - Status 模块

## 概述
`status.py` 提供系统状态监控 API，包括模型/Qdrant/Flask 状态、硬件信息、重启触发。

## 文件位置
```
backend/modules/status.py
```

## 路由注册
```python
def register(app, ready_state, logger, stats_db):
```
- `ready_state`：模型/Qdrant 就绪状态的共享字典引用
- `logger`：项目 logger 实例
- `stats_db`：统计数据库实例

## API 接口

### GET `/status`
**功能**：获取系统核心状态

**响应字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `model_loaded` | bool | embedding 模型是否已加载 |
| `qdrant_ready` | bool | Qdrant 是否就绪 |
| `device` | string | 当前设备（cpu/cuda） |
| `cuda_available` | bool | PyTorch CUDA 是否可用 |
| `gpu_hardware` | bool | 是否有 NVIDIA GPU 硬件（独立于 CUDA） |
| `gpu_name` | string/null | GPU 名称（CUDA 可用时） |
| `embedding_model` | string | embedding 模型名称 |
| `embedding_dim` | int | 向量维度（来自环境变量） |
| `model_size` | string | 模型参数量（B/M/K） |
| `qdrant_host` | string | Qdrant 主机 |
| `qdrant_port` | int | Qdrant 端口 |
| `qdrant_collection` | string | 集合名称 |
| `qdrant_top_k` | int | 默认 top_k |
| `qdrant_disk_size` | int | Qdrant 存储目录大小（字节） |
| `qdrant_storage_path` | string | 存储路径（相对路径） |
| `flask_port` | int | Flask 端口（来自 FLASK_PORT 环境变量） |
| `flask_pid` | int | 当前 Flask 进程 PID |
| `flask_uptime` | int | Flask 运行时长（秒） |
| `flask_reload` | bool | 是否开启了 Flask reload 模式 |

### GET `/system-info`
**功能**：获取详细硬件信息

**响应字段**：
| 字段 | 说明 |
|------|------|
| `cpu_percent` | CPU 使用率（0.1秒采样） |
| `memory_total/used/percent` | 内存信息 |
| `platform` | 完整平台字符串 |
| `os_name` | 操作系统名称 |
| `os_version` | OS 版本 |
| `python_version` | Python 版本 |
| `gpu` | GPU 信息对象（无 GPU 时为 null） |

**GPU 信息**（pynvml 可用时）：
```json
{
  "name": "NVIDIA GeForce RTX 4090",
  "memory_total": 25769803776,
  "memory_used": 1073741824,
  "memory_free": 24696061952,
  "memory_percent": 4,
  "temperature": 45
}
```

### GET `/db-status`
**功能**：检查统计数据库状态
```json
{ "ok": true, "daily_stats_count": 150, "stream_count": 2500, ... }
```

### POST `/flask/restart`
**功能**：手动重启 Flask（由 PM monitor 检测标志文件并执行重启）

**实现**：写入 `backend/.restart_flask` 标志文件
```json
{ "ok": true, "msg": "重启中...", "flag": "E:\\Project\\AiBrain\\backend\\.restart_flask" }
```

### GET `/memory-count`
**功能**：获取记忆总数（从 stats_db 读取）
```json
{ "count": 1234 }
```

### GET `/model-info`
**功能**：检查本地模型文件状态
```json
{
  "local_models_dir": "E:\\Project\\AiBrain\\models",
  "model_name": "BAAI/bge-m3",
  "local_path": "E:\\Project\\AiBrain\\models\\BAAI_bge-m3",
  "local_available": true,
  "hf_cache_available": true,
  "embedding_dim": 1024
}
```

## 内部函数

### `_has_nvidia_gpu()`
检测系统是否有 NVIDIA GPU 硬件（不依赖 CUDA 版 PyTorch）：
1. 优先用 pynvml → `nvmlDeviceGetCount() > 0`
2. Fallback：Windows WMIC 查询显卡名称，含 "nvidia" 则认为有 GPU

### `_get_qdrant_count_cached(settings, logger)`
启动时查询一次 Qdrant 存储大小，之后所有 `/status` 请求直接返回缓存值（`qdrant_disk_size` 和 `qdrant_storage_path`）。

## GPU 判断三状态
| cuda_available | gpu_hardware | 含义 |
|----------------|-------------|------|
| true | - | GPU 可用，CUDA 版 PyTorch 已安装 |
| false | true | 有 GPU 硬件但安装的是 CPU 版 PyTorch |
| false | false | 无 NVIDIA GPU |

## 相关模块
- **PM monitor**：检测 `.restart_flask` 标志文件，执行 Flask 重启
- **Overview 前端**：消费 `/status` 和 `/system-info` 数据
- **Settings 前端**：消费 `gpu_hardware` 显示 GPU 安装警告

---
*最后更新: 2026-05-01*
