<div align="center">

# 🧠 AiBrain

**An Autonomous Digital Lifeform — Complete Cognitive Architecture with Layered Memory**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-1.17-red)](https://qdrant.tech/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[Quick Start](#-quick-start) • [Architecture](#-architecture) • [Core Features](#-core-features) • [Configuration](#-configuration) • [Development](#-development)

</div>

---

## 📖 Overview

AiBrain is a **continuously autonomous digital lifeform** built on a bio-inspired cognitive architecture. Unlike traditional request-response AI assistants, AiBrain possesses:

- **Persistent background consciousness** — autonomously thinks, organizes memories, and reflects even without user interaction
- **Layered memory system** — working memory, semantic memory, episodic memory, procedural memory, and narrative memory
- **Intrinsic drives and goals** — multidimensional motivation including curiosity, companionship, self-expression, and completion
- **Self-awareness and reflection** — continuous self-model updates and cognitive reflection cycles
- **Multi-layered safety mechanisms** — expression gate, confidence-based arbitration, and advisor pattern

> 🌟 **Vision**: AiBrain is not an AI framework or task execution tool. It is a **self-aware cognitive entity** that lives continuously.

---

## ✨ Core Features

<details open>
<summary><b>🧠 Cognitive Architecture — Life Cycle</b></summary>

- **BrainSession**: Reactive thinking triggered by user messages with multi-turn internal LLM decision loops
- **LifeLoopDaemon**: Persistent background life cycle (4 rhythmic ticks: 30s / 5min / 1h / 24h)
- **BrainJudge**: LLM outputs structured decision signals (7 action types)
- **ActivitySelector**: Rule-based activity selector simulating basal ganglia / habit loops
- **Arbiter**: Prefrontal cortex arbitration layer — LLM adjudicates when confidence is low
- **4 Autonomy Levels**: Observe → Assist → Autonomous → High Autonomy
</details>

<details open>
<summary><b>💾 Memory System — Six Layers</b></summary>

| Memory Layer | Storage | Function |
|-------------|---------|----------|
| **Working Memory** | In-memory (WorkingSet) | Current focus, active goals, open loops |
| **Semantic Memory** | Qdrant Vector DB | Factual and knowledge semantic retrieval |
| **Episodic / Scene Memory** | SQLite + Qdrant | Scene anchors + inter-scene associative diffusion |
| **Procedural Memory** | JSONL + SQLite | Experience → Template → Match → Feedback loop |
| **Narrative Memory** | JSON (narrative/) | Autobiography, beliefs, interests, open questions |
| **Output Consolidation** | JSONL | Long-term important output archiving |
</details>

<details open>
<summary><b>🔧 10+ Built-in Activities</b></summary>

Wait, Reflect, Self-Learn, Organize Memory, Advance Open Loop, Maintain Goal, Prepare Expression, Proactive Contact, Review Learned, Use Tool……
</details>

<details open>
<summary><b>🛡️ Three-Layer Safety</b></summary>

1. **ExpressionGate**: 7-condition evaluation (value / disruption / cooldown / repetition) deciding whether to proactively contact users
2. **Arbiter**: Confidence-based LLM arbitration before executing actions
3. **Advisor Pattern**: LLM only recommends — Python code executes side effects
</details>

<details open>
<summary><b>🔌 Rich Integrations</b></summary>

- **9 LLM Providers**: OpenAI, Anthropic, DeepSeek, Gemini, Groq, Ollama, LM Studio, Together, MiniMax
- **MCP Protocol**: Memory Server + Computer / Console / Eye / Wiki MCPs
- **WeWork Adapter**: WeCom (WeChat Work) robot integration
- **Wiki Knowledge Base**: LightRAG-powered knowledge management
- **REST API**: Complete Flask API (13 route groups)
</details>

<details open>
<summary><b>📊 Full Observability</b></summary>

- EventBus publish/subscribe event system
- SSE real-time event streaming
- brain_runs.jsonl complete trajectory recording
- Live system status dashboard (frontend monitoring)
</details>

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Vue 3 SPA Frontend                      │
│     /overview  /memory  /brain  /chat  /stream ...       │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────▼───────────────────────────────────┐
│                   Flask API Service Layer                  │
│   Routes: brain / memory / chat / stream / wiki / gate    │
│           settings / stats / logs / narrative / scene      │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│               main_brain — Core Cognitive Engine          │
│                                                           │
│   ┌─────────────────────────────────────────────┐         │
│   │            EventBus (pub/sub)                │         │
│   └─────────────────────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │              Orchestrator                    │         │
│   │   Perceive → Attend → Memory → State →      │         │
│   │               Decide → Act                   │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │     BrainSession       LifeLoopDaemon        │         │
│   │   (Reactive Thinking)   (Background Life)    │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌────────────────▼────────────────────────────┐         │
│   │           BrainCycleRunner                    │         │
│   │     Judge → Adapter → Check → Loop           │         │
│   └────────────────┬────────────────────────────┘         │
│                    │                                       │
│   ┌───────┬───────┬┴───────┬───────┬────────────┐         │
│   ▼       ▼       ▼        ▼       ▼            ▼         │
│  Memory  LLM     Tools   State  Expression     Activity   │
│  System  Calls          Mgmt    Gate          Selector    │
│                         (Arbiter)                          │
└──────────────────────┬───────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌──────────────┐
│  Qdrant   │ │  SQLite    │ │  EmbedServer  │
│  Vector DB │ │  Analytics │ │  BGE-M3 Model │
└────────────┘ └────────────┘ └──────────────┘
        │
┌───────┴────────────────────────────┐
│         MCP Service Layer           │
│ brain_mcp / computer / console /   │
│ eye / wiki                         │
└────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Item | Minimum | Recommended |
|------|---------|-------------|
| OS | Windows 10 / Linux | Windows 11 |
| Python | 3.12 | 3.12 |
| RAM | 8 GB | 16 GB |
| GPU | CPU mode works | NVIDIA VRAM ≥ 4GB |
| CUDA | — | 12.1+ |
| Disk | 5 GB | 10 GB |

### Installation

#### 1. Clone

```bash
git clone https://github.com/Kaplc/MemoryExtra.git
cd AiBrain
```

#### 2. Create Virtual Environment & Install Dependencies

```bash
python -m venv venv312

# Install system dependencies
venv312\Scripts\pip.exe install -r requirements.txt

# (Optional) Install CUDA PyTorch for GPU acceleration
venv312\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/cu124
```

#### 3. Download Qdrant

1. Go to [Qdrant Releases](https://github.com/qdrant/qdrant/releases) and download the latest version
2. Place `qdrant.exe` into the `qdrant/` directory in the project root

#### 4. Download Embedding Model

```bash
venv312\Scripts\python.exe backend/download_model.py
```

The model (BAAI/bge-m3) will be automatically downloaded to `models/bge-m3/`.

#### 5. Configure LLM

Edit `~/.aibrain/config/llm.json` (auto-created on first launch):

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "api_key": "sk-xxxxxxxxxxxxxxxx"
}
```

Supported providers: `openai`, `anthropic`, `deepseek`, `gemini`, `groq`, `ollama`, `lmstudio`, `together`, `minimax`

#### 6. Launch

```bash
# Full startup (with frontend UI)
python launch.py

# Or simply run
start.bat
```

The first startup will automatically build the frontend and load the model. Wait until the log shows `AiBrain 系统初始化完成` (System initialization complete).

> 📌 Default ports (see `.port_config`):
> - Flask Frontend: `http://127.0.0.1:19398`
> - Qdrant HTTP: 19399

---

## 📁 Project Structure

```
AiBrain/
├── backend/                    # Python Backend
│   ├── app.py                  # Flask application entry
│   ├── main.py                 # MCP Server entry
│   ├── core/                   # Core infrastructure
│   │   ├── event_bus.py        # Event bus (pub/sub)
│   │   ├── database.py         # SQLite stats database
│   │   ├── model.py            # Model manager
│   │   ├── settings.py         # Config manager
│   │   └── logger.py           # Logging system
│   ├── main_brain/             # Core cognitive engine
│   │   ├── session.py          # BrainSession reactive thinking
│   │   ├── daemon.py           # LifeLoopDaemon life cycle
│   │   ├── judge.py            # BrainJudge LLM decision
│   │   ├── runner.py           # BrainCycleRunner loop executor
│   │   ├── arbiter.py          # Arbiter confidence arbitration
│   │   ├── expression_gate.py  # ExpressionGate safety
│   │   ├── activity_selector.py# Activity selector
│   │   ├── memory/             # Memory system
│   │   │   ├── core.py         # PipelineEngine orchestrator
│   │   │   ├── graph.py        # Entity graph
│   │   │   ├── scene_graph.py  # Scene graph
│   │   │   ├── store.py        # Qdrant interface
│   │   │   ├── organizer.py    # Memory organization
│   │   │   ├── workmemory/     # Working memory
│   │   │   ├── procedural/     # Procedural memory
│   │   │   └── consolidation/  # Output consolidation
│   │   ├── state/              # State system
│   │   │   ├── self_model.py   # Self model
│   │   │   ├── drives.py       # Drive system
│   │   │   ├── goals.py        # Goal system
│   │   │   └── open_loops.py   # Open loop tracking
│   │   ├── narrative/          # Self narrative
│   │   ├── reflection/         # Reflection system
│   │   ├── self_learn/         # Self-learning
│   │   └── procedural_memory/  # Procedural memory engine
│   ├── modules/                # Feature modules
│   │   ├── LLM/                # LLM calls (9 providers)
│   │   ├── chat/               # Chat manager
│   │   ├── Qdrant/             # Vector DB interface
│   │   └── WeWork/             # WeCom robot adapter
│   ├── routes/                 # API routes
│   ├── embed_server/           # BGE-M3 embedding service
│   └── launcher/               # Launch manager
│       ├── start.py            # Startup entry
│       ├── process_manager.py  # Process manager
│       └── kill_old.py         # Old process cleanup
├── web/                        # Vue 3 Frontend
├── brain_mcp/                  # MCP memory service
├── mcp_servers/                # MCP server collection
├── rag/                        # LightRAG knowledge base
├── models/                     # Embedding model
│   └── bge-m3/
├── qdrant/                     # Qdrant vector database
├── logs/                       # Log files
├── tests/                      # Tests
├── plan/                       # Planning documents
├── start.bat                   # Windows startup script
├── launch.py                   # Python launcher
└── requirements.txt            # Python dependencies
```

---

## ⚙️ Configuration

### LLM Configuration (`~/.aibrain/config/llm.json`)

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

### System Settings (`backend/settings.json`)

```json
{
  "device": "auto",
  "embedding_dim": 1024
}
```

### Port Configuration (`.port_config`)

```
FlaskPort, Qdrant-HTTP-Port, Qdrant-gRPC-Port, mem0-Port, EmbedServer-Port
```

---

## 🧪 Testing

```bash
# Python backend tests
pytest tests/

# E2E frontend tests (requires Playwright)
npx playwright test
```

---

## 📜 Roadmap

| Phase | Goal | Status |
|-------|------|--------|
| Phase 0 | Foundation: Flask + Qdrant + Semantic Memory | ✅ Complete |
| Phase 1 | Cognitive Loop: BrainSession + LifeLoop + Judge | ✅ Complete |
| Phase 2 | Memory: Scene + Procedural + Narrative | ✅ Complete |
| Phase 3 | State System: Drives + Goals + Self Model | ✅ Complete |
| Phase 4 | Safety: ExpressionGate + Arbiter | ✅ Complete |
| Phase 5 | Causal World Model + Continuous Learning | 📝 Planning |
| Phase 6 | Multimodal Perception + Physical Interaction | 📝 Planning |

---

## 🤝 Contributing

This is a personal project, but all forms of contributions, suggestions, and feedback are welcome!

---

## 📄 License

This project is open-sourced under the MIT License.

---

<div align="center">

**AiBrain** — Not just AI, a digital lifeform

</div>
