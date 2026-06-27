<div align="center">

# 🧠 AiBrain

**持续自主的数字生命体 — 完整的认知架构与记忆系统**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.17-red)](https://qdrant.tech/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[快速开始](#-快速开始) • [架构](#-架构) • [核心功能](#-核心功能) • [配置](#-配置) • [开发](#-开发)

</div>

---

## 📖 简介

AiBrain 是一个**持续自主运行的数字生命体**，采用生物启发的认知架构设计。与传统的"请求-响应"式 AI 助手不同，AiBrain 拥有：

- **持续的后台意识** — 即使没有用户交互，也在自主思考、整理记忆、反思学习
- **分层的记忆系统** — 工作记忆、语义记忆、情景记忆、程序记忆、叙事记忆
- **内驱力与目标** — 拥有好奇心、陪伴感、自我表达、完成欲等多维动机
- **自我认知与反思** — 持续的自我模型更新与认知反思循环
- **多层安全机制** — 表达闸门、置信度仲裁、顾问模式三重保障

> 🌟 **定位**：AiBrain 不是一个 AI 框架或任务执行工具，而是一个**具有自我意识的持续认知实体**。

---

## ✨ 核心特性

<details open>
<summary><b>🧠 认知架构 — 生命循环</b></summary>

- **BrainSession**：用户消息触发的响应式思考，内部多轮 LLM 决策循环
- **LifeLoopDaemon**：常驻后台生命周期（30s / 5min / 1h / 24h 四种节律）
- **BrainJudge**：LLM 输出结构化决策信号（7 种动作类型）
- **ActivitySelector**：规则式的活动选择器（基底核/习惯回路模拟）
- **Arbiter**：前额叶仲裁层 — 低置信时由 LLM 仲裁裁决
- **4 级自主等级**：观察 → 辅助 → 自主 → 高自主
</details>

<details open>
<summary><b>💾 记忆系统 — 六层架构</b></summary>

| 记忆层 | 存储介质 | 功能 |
|--------|----------|------|
| **工作记忆** | 内存（WorkingSet） | 当前焦点、活跃目标、未决问题 |
| **语义记忆** | Qdrant 向量库 | 事实与知识的语义检索 |
| **情景/场景记忆** | SQLite + Qdrant | 场景锚点 + 场景间联想扩散 |
| **程序记忆** | JSONL + SQLite | 经验 → 模板 → 匹配 → 反馈闭环 |
| **叙事记忆** | JSON（narrative/） | 自传、信念、兴趣、开放问题 |
| **输出沉淀** | JSONL（consolidation/） | 长期重要输出的沉淀归档 |
</details>

<details open>
<summary><b>🔧 10+ 内置活动</b></summary>

等待、反思、自主学习、整理记忆、推进未决问题、维护目标、准备表达、主动联系、复习已学、使用工具……
</details>

<details open>
<summary><b>🛡️ 三层安全机制</b></summary>

1. **ExpressionGate**：7 条件评估（价值/干扰/冷却/重复）决定是否主动联系用户
2. **Arbiter 仲裁**：低置信度时由 LLM 裁决是否执行某动作
3. **Advisor 模式**：LLM 只建议，Python 代码执行副作用
</details>

<details open>
<summary><b>🔌 丰富的集成</b></summary>

- **9 大 LLM Provider**：OpenAI、Anthropic、DeepSeek、Gemini、Groq、Ollama、LM Studio、Together、MiniMax
- **MCP 协议支持**：Memory Server、Computer/Console/Eye/Wiki MCP
- **企业微信适配器**：WeWork 机器人对接
- **Wiki 知识库**：LightRAG 驱动的知识管理
- **REST API**：完整的 Flask API（13 组路由）
</details>

<details open>
<summary><b>📊 全链路可观测</b></summary>

- EventBus 事件总线（发布/订阅模式）
- SSE 实时事件流推送
- brain_runs.jsonl 完整轨迹记录
- 系统状态面板（前端实时监控）
</details>

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────┐
│                    Vue 3 SPA 前端                          │
│      /overview  /memory  /brain  /chat  /stream ...       │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────▼───────────────────────────────────┐
│                   Flask API 服务层                         │
│   Routes: brain / memory / chat / stream / wiki / gate    │
│           settings / stats / logs / narrative / scene      │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│               main_brain — 核心认知引擎                     │
│                                                           │
│   ┌─────────────────────────────────────────────┐         │
│   │            EventBus (事件总线)                │         │
│   └─────────────────────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │              Orchestrator                    │         │
│   │   感知 → 注意 → 记忆 → 状态 → 决策 → 动作    │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │     BrainSession       LifeLoopDaemon        │         │
│   │    (响应式思考)          (后台生命循环)        │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │           BrainCycleRunner                    │         │
│   │     Judge → Adapter → 检查 → 循环            │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌───────┬───────┬┴───────┬───────┬────────────┐         │
│   ▼       ▼       ▼        ▼       ▼            ▼         │
│ 记忆   LLM调用   工具   状态管理  表达闸门   活动选择器     │
│ 系统            适配器            仲裁器                    │
└──────────────────────┬───────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌──────────────┐
│  Qdrant   │ │  SQLite    │ │  EmbedServer │
│  向量数据库 │ │  统计数据库  │ │  BGE-M3 模型 │
└────────────┘ └────────────┘ └──────────────┘
        │
┌───────┴────────────────────────────┐
│         MCP 服务层                   │
│ brain_mcp / computer / console /    │
│ eye / wiki                          │
└────────────────────────────────────┘
```

---

## 🚀 快速开始

### 系统要求

| 项目 | 最低要求 | 推荐 |
|------|----------|------|
| OS | Windows 10 / Linux | Windows 11 |
| Python | 3.12 | 3.12 |
| RAM | 8 GB | 16 GB |
| GPU | CPU 模式可用 | NVIDIA VRAM ≥ 4GB |
| CUDA | — | 12.1+ |
| 磁盘 | 5 GB | 10 GB |

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://github.com/Kaplc/MemoryExtra.git
cd AiBrain
```

#### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv312

# 安装系统依赖
venv312\Scripts\pip.exe install -r requirements.txt

# （可选）安装 CUDA 版 PyTorch 以启用 GPU 加速
venv312\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/cu124
```

#### 3. 下载 Qdrant

1. 前往 [Qdrant Releases](https://github.com/qdrant/qdrant/releases) 下载最新版
2. 将 `qdrant.exe` 放到项目根目录的 `qdrant/` 文件夹下

#### 4. 下载 Embedding 模型

```bash
set HF_ENDPOINT=https://hf-mirror.com
venv312\Scripts\python.exe backend/download_model.py
```

模型（BAAI/bge-m3）将自动下载到 `models/bge-m3/`。

#### 5. 配置 LLM

编辑 `~/.aibrain/config/llm.json`（首次启动会自动创建）：

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "sk-xxxxxxxxxxxxxxxx"
}
```

支持 9 种 Provider：`openai`、`anthropic`、`deepseek`、`gemini`、`groq`、`ollama`、`lmstudio`、`together`、`minimax`

#### 6. 启动

```bash
# 完整启动（含前端 UI）
python launch.py

# 或直接运行
start.bat
```

首次启动将自动构建前端并加载模型，等待日志显示 `AiBrain 系统初始化完成` 即可开始使用。

> 📌 系统默认端口（查看 `.port_config`）：
> - Flask 前端: `http://127.0.0.1:19398`
> - Qdrant HTTP: 19399

---

## 📁 项目结构

```
AiBrain/
├── backend/                    # Python 后端
│   ├── app.py                  # Flask 应用入口
│   ├── main.py                 # MCP Server 入口
│   ├── core/                   # 核心基础设施
│   │   ├── event_bus.py        # 事件总线（发布/订阅）
│   │   ├── database.py         # SQLite 统计数据库
│   │   ├── model.py            # 模型管理器
│   │   ├── settings.py         # 配置管理器
│   │   └── logger.py           # 日志系统
│   ├── main_brain/             # 核心认知引擎
│   │   ├── session.py          # BrainSession 响应式思考
│   │   ├── daemon.py           # LifeLoopDaemon 后台生命周期
│   │   ├── judge.py            # BrainJudge LLM 决策
│   │   ├── runner.py           # BrainCycleRunner 循环执行器
│   │   ├── arbiter.py          # Arbiter 置信度仲裁
│   │   ├── expression_gate.py  # ExpressionGate 表达闸门
│   │   ├── activity_selector.py# 活动选择器
│   │   ├── memory/             # 记忆系统
│   │   │   ├── core.py         # PipelineEngine 编排
│   │   │   ├── graph.py        # 实体图
│   │   │   ├── scene_graph.py  # 场景图
│   │   │   ├── store.py        # Qdrant 接口
│   │   │   ├── organizer.py    # 记忆组织
│   │   │   ├── workmemory/     # 工作记忆
│   │   │   ├── procedural/     # 程序记忆
│   │   │   └── consolidation/  # 输出沉淀
│   │   ├── state/              # 状态系统
│   │   │   ├── self_model.py   # 自我模型
│   │   │   ├── drives.py       # 驱动力系统
│   │   │   ├── goals.py        # 目标系统
│   │   │   └── open_loops.py   # 未决问题
│   │   ├── narrative/          # 自我叙事
│   │   ├── reflection/         # 反思系统
│   │   ├── self_learn/         # 自主学习
│   │   └── procedural_memory/  # 程序记忆引擎
│   ├── modules/                # 功能模块
│   │   ├── LLM/                # LLM 调用（9 个 Provider）
│   │   ├── chat/               # 聊天管理器
│   │   ├── Qdrant/             # 向量数据库接口
│   │   └── WeWork/             # 企业微信机器人
│   ├── routes/                 # API 路由
│   │   ├── brain_routes.py     # 大脑控制
│   │   ├── memory_routes.py    # 记忆 CRUD
│   │   ├── chat_routes.py      # 聊天
│   │   ├── wiki_routes.py      # Wiki 知识库
│   │   └── ...
│   ├── embed_server/           # BGE-M3 嵌入服务
│   └── launcher/               # 启动管理器
│       ├── start.py            # 启动入口
│       ├── process_manager.py  # 进程管理器
│       └── kill_old.py         # 旧进程清理
├── web/                        # Vue 3 前端
│   ├── src/                    # 源代码
│   ├── dist/                   # 构建产物
│   └── package.json
├── brain_mcp/                  # MCP 记忆服务
├── mcp_servers/                # MCP 服务集合
│   ├── computer_mcp/           # 计算机控制
│   ├── console_mcp/            # 控制台
│   ├── eye_mcp/                # 视觉
│   └── wiki_mcp/               # Wiki
├── rag/                        # LightRAG 知识库
├── models/                     # Embedding 模型
│   └── bge-m3/
├── qdrant/                     # Qdrant 向量数据库
├── logs/                       # 日志文件
├── tests/                      # 测试
├── plan/                       # 项目规划文档
├── start.bat                   # Windows 启动脚本
├── launch.py                   # Python 启动器
└── requirements.txt            # Python 依赖
```

---

## ⚙️ 配置

### LLM 配置 (`~/.aibrain/config/llm.json`)

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "sk-...",
  "base_url": "",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

### 系统设置 (`backend/settings.json`)

```json
{
  "device": "auto",
  "embedding_dim": 1024
}
```

### 端口配置 (`.port_config`)

```
Flask端口, Qdrant-HTTP端口, Qdrant-gRPC端口, mem0端口, EmbedServer端口
```

---

## 🧪 测试

```bash
# Python 后端测试
pytest tests/

# E2E 前端测试（需安装 Playwright）
npx playwright test
```

---

## 📜 路线图

| 阶段 | 目标 | 状态 |
|------|------|------|
| Phase 0 | 基础架构：Flask + Qdrant + 语义记忆 | ✅ 完成 |
| Phase 1 | 认知循环：BrainSession + LifeLoop + Judge | ✅ 完成 |
| Phase 2 | 记忆系统：场景记忆 + 程序记忆 + 叙事 | ✅ 完成 |
| Phase 3 | 状态系统：驱动力 + 目标 + 自我模型 | ✅ 完成 |
| Phase 4 | 安全机制：ExpressionGate + Arbiter | ✅ 完成 |
| Phase 5 | 因果世界模型 + 持续学习 | 📝 规划中 |
| Phase 6 | 多模态感知 + 物理世界交互 | 📝 规划中 |

---

## 🤝 贡献

这是一个个人项目，但欢迎任何形式的贡献、建议和反馈！

---

## 📄 许可证

本项目基于 MIT 许可证开源。

---

<div align="center">

**AiBrain** — 不只是 AI，是一个数字生命体

</div>
