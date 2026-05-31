# AiBrain 项目大纲

```
[PyWebView 桌面壳] → [Vue 3 前端 SPA] → API → [Flask 3.1 后端] → [Qdrant / SQLite / LightRAG]
                                                                   → [MCP Servers (Brain/Wiki/Computer/Console/Eye)]
```
- **后端**: Flask 3.1 REST API
- **前端**: Vue 3 + TypeScript + Pinia + Vite 6
- **桌面壳**: PyWebView 6
- **向量库**: Qdrant | **图存储**: SQLite + NetworkX | **RAG**: LightRAG
- **嵌入模型**: BAAI/bge-m3

## 子目录详情
| 目录 | 说明 | 文档 |
|------|------|------|
| `backend/` | Flask 后端 (core/routes/modules/launcher) | `backend/CLAUDE.md` |
| `web/` | Vue 3 前端 (views/stores/composables) | `web/CLAUDE.md` |
| `brain_mcp/` | 核心 MCP 记忆服务器 | `brain_mcp/CLAUDE.md` |
| `mcp_servers/` | 扩展 MCP (wiki/computer/console/eye) | `mcp_servers/CLAUDE.md` |
| `tests/` | pytest + Playwright 测试 | `tests/CLAUDE.md` |

## 技术栈
- **Python**: Flask 3.1, FastMCP, qdrant-client, mem0ai, lightrag-hku, sentence-transformers, torch
- **前端**: Vue 3 + Pinia 3 + Vue Router 4 + Vite 6 + TypeScript 5.8
- **可视化**: ECharts 6, @antv/g6 5, force-graph, three.js, 3d-force-graph
- **数据库**: Qdrant (向量) + SQLite (图/统计/流)
- **桌面**: PyWebView 6

## 重要提醒

1-logs\这里是放日志的目录

2-AiBrain\.port_config这个是后端的接口要测试和访问就使用这个

3-.claude\plan\这里是放项目计划的目录

4-这个是 @app.route('/overview/flask/restart', methods=['POST'])手动重启后端修改后端文件后可以使用这个接口重启后端

5-后端刚启动需要预热加载语义模型不能马上请求记忆查询和保存，可以请求一下语义模型状态的接口来确认是否预热完成
@app.route('/overview/model', methods=['GET'])

