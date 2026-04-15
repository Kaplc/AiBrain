# MemoryExtra 环境配置指南

本项目依赖本地 Embedding 模型（BAAI/bge-m3）和 Qdrant 向量数据库，均不包含在仓库中，需手动下载配置。

---

## 目录结构（配置完成后）

```
MemoryExtra/
├── models/
│   └── bge-m3/          ← 需要手动下载
├── venv312/             ← 需要手动创建
├── app.py
├── main.py
├── start_qdrant.bat
└── mcp_qdrant/

Desktop/
└── qdrant/
    └── qdrant.exe       ← 需要手动下载
```

---

## 第一步：安装 Python 3.12

下载并安装 Python 3.12：https://www.python.org/downloads/

安装时勾选 **Add Python to PATH**。

---

## 第二步：创建虚拟环境并安装依赖

```bash
cd C:\Users\你的用户名\Desktop\MemoryExtra

# 创建虚拟环境
python -m venv venv312

# 安装依赖（先安装 CPU 版 torch 以外的包）
venv312\Scripts\pip.exe install flask flask-cors pywebview fastmcp qdrant-client sentence-transformers pydantic-settings

# 安装 CUDA 版 PyTorch（需要 NVIDIA 显卡 + CUDA 驱动）
venv312\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/cu121

# 如果没有 NVIDIA 显卡，安装 CPU 版（速度较慢）
# venv312\Scripts\pip.exe install torch
```

---

## 第三步：下载 Qdrant

1. 前往 https://github.com/qdrant/qdrant/releases 下载最新 Windows 版本
2. 解压，将 `qdrant.exe` 放到以下路径：

```
C:\Users\你的用户名\Desktop\qdrant\qdrant.exe
```

---

## 第四步：下载 bge-m3 模型

模型较大（约 2GB），从 HuggingFace 或镜像站下载。

### 方式一：使用 Python 脚本下载

```bash
# 设置镜像（国内推荐）
set HF_ENDPOINT=https://hf-mirror.com

venv312\Scripts\python.exe download_model.py
```

### 方式二：手动下载

从以下地址下载所有文件：
- 官方：https://huggingface.co/BAAI/bge-m3
- 镜像：https://hf-mirror.com/BAAI/bge-m3

**必须下载的文件：**
```
config.json
config_sentence_transformers.json
modules.json
sentence_bert_config.json
sentencepiece.bpe.model
special_tokens_map.json
tokenizer.json
tokenizer_config.json
model.safetensors          ← 主模型文件（约 2.2GB）
colbert_linear.pt
sparse_linear.pt
1_Pooling/config.json
```

将所有文件放到：
```
MemoryExtra\models\bge-m3\
```

> **注意**：如果下载的是 `pytorch_model.bin` 而非 `model.safetensors`，需要转换格式：
> ```bash
> venv312\Scripts\python.exe -c "
> import torch
> from safetensors.torch import save_file
> state_dict = torch.load('models/bge-m3/pytorch_model.bin', map_location='cpu', weights_only=False)
> save_file(state_dict, 'models/bge-m3/model.safetensors')
> print('转换完成')
> "
> ```

---

## 第五步：配置 Claude Code MCP

在项目根目录已有 `.mcp.json`，将其中的用户名路径替换为你自己的：

```json
{
  "mcpServers": {
    "qdrant-memory": {
      "type": "stdio",
      "command": "C:\\Users\\你的用户名\\Desktop\\MemoryExtra\\venv312\\Scripts\\python.exe",
      "args": ["C:\\Users\\你的用户名\\Desktop\\MemoryExtra\\main.py"]
    }
  }
}
```

同时修改 `app.py` 中第 17 行的 qdrant 路径：

```python
os.environ.setdefault('QDRANT_EXE_PATH', r'C:\Users\你的用户名\Desktop\qdrant\qdrant.exe')
```

---

## 第六步：启动

双击运行：

```
MemoryExtra\start_qdrant.bat
```

该脚本会自动：
1. 启动 Qdrant 数据库
2. 启动 Memory Manager 前端窗口
3. 后台加载 bge-m3 模型（约 25 秒，GPU）

等待前端右上角状态从 **"模型加载中..."** 变为 **"模型已就绪"** 即可正常使用。

---

## 系统要求

| 项目 | 最低要求 | 推荐 |
|------|----------|------|
| OS | Windows 10 | Windows 11 |
| Python | 3.12 | 3.12 |
| RAM | 8GB | 16GB |
| 显卡 | 无（CPU模式）| NVIDIA（VRAM ≥ 4GB） |
| CUDA | - | 12.1 或 12.2 |
| 磁盘 | 5GB | 10GB |

---

## 常见问题

**Q: 启动后一直显示"模型加载中"**
- 检查 `models/bge-m3/model.safetensors` 是否存在
- 确认 `app.py` 中模型路径正确

**Q: store/search 报错"Memory服务未启动"**
- 确保先运行了 `start_qdrant.bat`
- 检查 `http://127.0.0.1:18765/status` 是否可访问

**Q: CUDA 不可用，速度很慢**
- 确认安装的是 CUDA 版 PyTorch：`venv312\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"`
- 如输出 False，重新安装：`pip install torch --index-url https://download.pytorch.org/whl/cu121`

**Q: qdrant 连接失败**
- 确认 `qdrant.exe` 路径正确
- 手动运行 `qdrant.exe` 查看是否有报错
