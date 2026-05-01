# 前端 - Wiki 模块（知识库）

## 模块概述
Wiki模块提供知识库文件管理和索引管理功能，集成LightRAG引擎。采用两栏布局：左侧文件列表，右侧带导航切换的信息面板（统计/操作/设置三个tab）。

## 文件位置
```
web/modules/wiki/
├── wiki.html            # HTML模板 + CSS（内联），根div带 data-deps 属性
├── wiki.js              # 页面逻辑（入口 onPageLoad）
├── wiki_file.js         # WikiFile 类 + _createWikiFiles 工厂函数（JS依赖）
├── wiki_stats.html      # 统计面板HTML片段（slot-stats）
├── wiki_ops.html        # 操作面板HTML片段（slot-ops）
└── wiki_settings.html   # 设置面板HTML片段（slot-settings）
```

## 加载机制（data-deps）

Wiki 页面采用 router 的 HTML 片段并行加载机制。`wiki.html` 根 div 声明 `data-deps`：

```html
<div class="wiki-wrap" data-deps="wiki_file,wiki_stats.html,wiki_ops.html,wiki_settings.html">
```

- `.html` 后缀 → HTML 片段，并行 fetch 后塞入 `<div id="slot-{映射名}">`
- 无后缀 → JS 依赖，主脚本加载完后按顺序串行加载（`wiki_file.js` → `wiki.js`）

**slot 映射规则**（`slotMap`）：
| 片段文件 | slot ID |
|---------|---------|
| `wiki_stats.html` | `slot-stats` |
| `wiki_ops.html` | `slot-ops` |
| `wiki_settings.html` | `slot-settings` |

路由 slot 查找使用 `document.getElementById()`，必须在 `innerHTML` 设置后执行。

## 界面布局

### 两栏结构
```
┌──────────────────────────────────────────────────┐
│ Wiki 知识库                            [统计][操作][设置] │  ← header + 右侧tab导航
├──────────────────────────┬───────────────────────┤
│                          │  统计面板              │
│   文件列表表格            │  文件数/总大小/索引状态 │
│   （可排序、点击复制路径）│                       │
│                          ├───────────────────────┤
│                          │  操作面板              │
│                          │  重建索引按钮          │
│                          │  进度条 + 索引日志      │
│                          ├───────────────────────┤
│                          │  设置面板              │
│                          │  目录/LLM/分块配置     │
└──────────────────────────┴───────────────────────┘
```

### 右侧面板Tab
| Tab | 内容 | slot ID |
|-----|------|---------|
| 统计 | 文件数、总大小、索引状态（已同步/需重建/未索引） | `slot-stats` |
| 操作 | 重建索引按钮 + 进度条 + 索引日志 + 结果反馈 | `slot-ops` |
| 设置 | Wiki目录、LightRAG目录、语言、分块大小、超时 | `slot-settings` |

### 右侧HTML元素
| ID | 类型 | 说明 |
|----|------|------|
| `sidePanelStats` | div | 统计面板容器 |
| `sidePanelOps` | div | 操作面板容器 |
| `sidePanelSettings` | div | 设置面板容器 |
| `btnReindex` | button | 重建索引按钮 |
| `indexProgressWrap` | div | 进度条外层（display控制显隐） |
| `indexProgressFill` | div | 进度条填充（width控制百分比） |
| `indexProgressPct` | span | 百分比文字 |
| `indexProgressLabel` | div | 当前索引文件名 + 进度文字 |
| `indexLogWrap` | div | 索引日志实时显示 |
| `indexResult` | div | 索引结果（成功/失败提示） |

## 交互逻辑流

### 页面加载（onPageLoad）
```
onPageLoad()
  ├── loadWikiConfig()            ← 加载配置到 _wikiConfig
  ├── loadWikiData()             ← 加载文件列表
  └── restoreIndexProgress()      ← 恢复索引进度UI + 启动轮询
```

### 索引进度恢复（restoreIndexProgress）
```
restoreIndexProgress()
  → GET /wiki/index-progress
  → 如 status='running'：显示进度UI，按钮禁用，恢复进度
  → 始终调用 startIndexPoll()
```

### 索引进度轮询（startIndexPoll，500ms间隔）
```
startIndexPoll() (每500ms)
  → GET /wiki/index-progress
  ├── status='running':
  │     → 按钮禁用，文字='索引中...'
  │     → 显示进度条，填充 width=(done/total*100)%
  │     → 标签显示: '索引: filename (done/total)'
  │     → refreshIndexLog() 刷新索引日志
  │     → 如 done 变化 → loadWikiData() 刷新文件列表
  │     → 更新 _lastIndexDone
  └── status != 'running':
        → 如 _lastIndexDone != -1（之前是running）:
              → 隐藏进度条，恢复按钮
              → 清空索引日志
              → loadWikiData() 刷新文件列表
              → 如 status='done' → 显示绿色提示
              → 如 status='error' → 显示红色提示
              → 重置 _lastIndexDone = -1
```

### 索引日志刷新（refreshIndexLog，500ms轮询中调用）
```
refreshIndexLog(container)
  → GET /wiki/index-log?lines=20
  → 每行包装成 .log-line div
  → 追加到 container，滚动到底部
  → 最后一行高亮（opacity:1, color:white）
```

### 重建索引触发（rebuildIndex）
```
rebuildIndex()
  → 按钮禁用，文字='索引中...'
  → 显示进度条，填充归零
  → 重置 _lastIndexDone = 0
  → POST /wiki/index
  ├── 返回 error → 隐藏进度条，显示错误提示，恢复按钮
  └── 返回成功 → startIndexPoll() 启动轮询（共享定时器）
```

### 右侧面板切换（switchSideTab）
```
switchSideTab('stats')
  → 切换 tab active 样式
  → 显示 sidePanelStats

switchSideTab('ops')
  → 切换 tab active 样式
  → 显示 sidePanelOps
  → restoreIndexProgress() 恢复索引UI状态

switchSideTab('settings')
  → 切换 tab active 样式
  → 显示 sidePanelSettings
  → loadWikiSettingsData() 加载配置表单
```

## 数据流

### API 接口
```
GET  /wiki/list                  → 获取文件列表
POST /wiki/index                → 触发索引重建
GET  /wiki/index-progress       → 获取索引进度
GET  /wiki/index-log?lines=20   → 获取索引过程日志
GET  /wiki/settings             → 获取wiki配置
POST /wiki/settings             → 保存wiki配置
```

### 索引进度响应（GET /wiki/index-progress）
```json
{ "status": "running", "done": 12, "total": 30, "current_file": "笔记.md" }
{ "status": "done", "done": 30, "total": 30 }
{ "status": "error", "error": "文件读取失败" }
```

### 索引日志响应（GET /wiki/index-log?lines=20）
```json
{ "lines": ["[2026-04-30 14:30] 开始索引...", "[2026-04-30 14:30] 索引: 笔记.md (1/30)"] }
```

### 文件列表响应（GET /wiki/list）
```json
{
  "files": [
    {
      "filename": "前端-overview模块.md",
      "abs_path": "E:\\Project\\AiBrain\\wiki\\project\\前端-overview模块.md",
      "size_bytes": 5120,
      "modified": 1746012345,
      "preview": "系统首页，展示模型...",
      "index_status": "synced"
    }
  ],
  "indexed": true
}
```

### index_status 枚举
| 值 | 图标 | 含义 |
|----|-----|------|
| `synced` | ✓(绿色) | 文件已索引，与索引一致 |
| `out_of_sync` | ⚠(橙色) | 文件已修改，需重建索引 |
| 其他 | ○(灰色) | 未索引 |

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：加载配置 + 文件列表 + 索引进度 |
| `cleanup()` | 清除 `_indexPollTimer` 定时器 |
| `restoreIndexProgress()` | 恢复索引进度UI（页面加载时调用） |
| `startIndexPoll()` | 500ms轮询进度，共享定时器（防重复创建） |
| `refreshIndexLog(container)` | 获取并显示索引过程日志 |
| `loadWikiConfig()` | 加载配置到 `_wikiConfig` |
| `loadWikiData()` | 加载文件列表，更新统计卡片和表格 |
| `rebuildIndex()` | POST 触发索引重建，按钮loading状态 |
| `switchSideTab(tab)` | 切换右侧tab（stats/ops/settings） |
| `loadWikiSettingsData()` | 加载设置表单数据 |
| `saveWikiSettings()` | POST 保存配置 |
| `renderTable(files)` | 渲染文件表格（排序、点击复制） |
| `sortFiles(key)` | 按字段排序（filename/size_bytes/modified） |
| `copyPath(path, row)` | 点击行复制文件路径 |

## WikiFile 类（wiki_file.js）

`WikiFile` 类和 `_createWikiFiles()` 工厂函数定义在 `wiki_file.js`，由 router 作为 JS 依赖加载（在 `wiki.js` 之前）。

```javascript
class WikiFile { constructor(d) { ... } toRowHtml() { ... } }
function _createWikiFiles(files) { return files.map(f => new WikiFile(f)); }
```

## 全局状态
```javascript
var _wikiFiles = [];         // 文件列表数据
var _sortKey = 'modified';   // 当前排序字段
var _sortAsc = false;        // 排序方向
var _wikiConfig = null;      // wiki配置对象
var _indexPollTimer = null;  // 索引进度轮询定时器（500ms）
var _lastIndexDone = -1;     // 上次已完成的文件数（判断是否需刷新列表）
```

## 后端相关文件
| 文件 | 作用 |
|------|------|
| `backend/modules/wiki_mod.py` | Flask路由，提供 `/wiki/*` REST API |
| `rag/lightrag_wiki/config.py` | wiki/lightrag目录配置、索引元数据路径 |
| `rag/lightrag_wiki/indexer.py` | 文件索引器（sync_index、index_single_file） |
| `rag/lightrag_wiki/rag_engine.py` | RAG搜索引擎 |

## 相关模块
- **设置模块** (`web/modules/settings/`): 全局设置页也包含wiki配置tab
- **Wiki MCP** (`brain_mcp/`): 提供 wiki_search / wiki_list / wiki_index 的MCP工具

---
*最后更新: 2026-05-01*
