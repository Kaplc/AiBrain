# AiBrain 架构

> 详细架构分析请参阅：[AiBrain架构详细分析.md](./AiBrain架构详细分析.md)

## 技术栈概览
- **后端框架**: Flask + PyWebView (桌面应用外壳)
- **向量数据库**: Qdrant (本地向量存储)
- **嵌入模型**: BGE-M3 (1024维，本地离线)
- **记忆引擎**: mem0 (自适应记忆管理)
- **知识库系统**: LightRAG (知识图谱增强RAG)
- **前端技术**: 原生 HTML/JavaScript/CSS (SPA架构)

## 核心服务模块
- **brain_mcp**: 记忆存储与检索 MCP 服务
- **wiki_mcp**: Wiki 知识库搜索与管理 MCP 服务  
- **eye_mcp**: 屏幕截图与视觉识别 MCP 服务
- **console_mcp**: 控制台交互 MCP 服务
- **computer_mcp**: 计算机操作 MCP 服务

## 系统架构层次
1. **前端层**: PyWebView + Web SPA
2. **API层**: Flask RESTful 服务
3. **记忆层**: mem0 + Qdrant + BGE-M3
4. **知识层**: LightRAG + Wiki 系统
5. **MCP层**: 标准化工具服务
6. **进程层**: 统一进程管理

## 关键特性
- ✅ 完全本地化运行，无外部依赖
- ✅ 自适应搜索策略 (根据数据量自动优化)
- ✅ 多进程隔离管理 (Qdrant/Flask/UI分离)
- ✅ 知识图谱增强检索 (LightRAG)
- ✅ 标准化MCP工具集成
- ✅ 离线模型支持 (BGE-M3本地嵌入)
