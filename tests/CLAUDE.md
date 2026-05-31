# tests/ — 测试套件

## 概览
双测试体系：pytest (Python 后端逻辑) + Playwright (前端 E2E)。

## Python 测试 (pytest)
| 文件 | 说明 |
|------|------|
| `test_brain_network.py` | 大脑网络核心逻辑 |
| `test_graph.py` | 图记忆层测试 |
| `test_migrate.py` | 记忆迁移测试 |
| `test_organizer.py` | 记忆整理 (聚类/精炼) 测试 |
| `test_embedding.py` | 嵌入生成测试 |
| `test_tools.py` | MCP 工具测试 |
| `test_integration.py` | 集成测试 |
| `test_config.py` | 配置管理测试 |
| `test_server.py` | Flask 服务器测试 |
| `test_flask_restart.py` | Flask 重启测试 |
| `e2e_wiki_index.py` | Wiki 索引端到端 |
| `e2e_wiki_page_load.py` | Wiki 页面加载端到端 |

## E2E 测试 (Playwright)
| 文件 | 说明 |
|------|------|
| `app.spec.ts` | 应用整体测试 |
| `memory-search.spec.ts` | 记忆搜索 |
| `graph.spec.ts` / `graph-tab.spec.ts` | 图谱可视化 |
| `graph-v2.spec.ts` | 图谱 V2 |
| `graph-deep-search.spec.ts` | 图谱深度搜索 |
| `graph-entity-search.spec.ts` | 图谱实体搜索 |
| `overview-chart-yaxis.spec.ts` | 概览图 Y 轴 |
| `wiki.spec.ts` / `wiki-progress.spec.ts` | Wiki 功能 |
| `wiki-fileitem-state.spec.ts` | Wiki 文件项状态 |
| `stream-entity-tags.spec.ts` | 流实体标签 |
| `chart-yaxis-visual.spec.ts` | 图表 Y 轴视觉 |
| `tab-switch-stability.spec.ts` | 标签切换稳定性 |
| `settings.spec.ts` | 设置页面 |
