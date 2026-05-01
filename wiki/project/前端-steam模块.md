# 前端 - Steam 模块（记忆流）

## 模块概述
记忆流页面，双栏布局展示 MCP 调用记录和查询记录。2 秒轮询全量列表 + 1 秒轮询 pending 状态，增量 DOM 更新避免闪烁。

## 文件位置
```
web/modules/steam/
├── steam.html   # HTML模板 + CSS（内联）
└── steam.js     # 页面逻辑
```

## 界面布局
```
┌─────────────────────────────────────────────────────┐
│ 记忆流                        MCP 12 条 / 搜索 8 条  │  ← 总计数
├─────────────────────┬───────────────────────────────┤
│ ● MCP调用            │ ● 查询记忆                    │
│  存入 文本...  ✓      │  搜索 关键词    ✓              │
│  存入 文本...  ⟳      │  搜索 关键词    ⟳              │  ← ⟳=pending
│  存入 文本...  ✗      │  搜索 关键词    ✓              │  ← ✗=error
└─────────────────────┴───────────────────────────────┘
```

## 交互逻辑流

### 页面加载（onPageLoad）
```
onPageLoad()
  ├── loadStream()                ← 立即加载一次全量
  ├── setInterval(loadStream, 2000)  ← 2秒轮询全量列表
  └── startStatusPoll()             ← 1秒轮询 pending 状态
```

### 主轮询（2秒间隔）
```
loadStream() (每2秒)
  ├── 并行请求:
  │     ├── GET /stream?action=store&days=3    ← MCP调用记录
  │     └── GET /stream?action=search&days=3  ← 查询记录
  ├── 更新总计数和各栏计数
  ├── renderList('storeList', storeItems)     ← 增量更新左侧
  └── renderList('searchList', searchItems)    ← 增量更新右侧
```

### 状态轮询（1秒间隔，仅有 pending 时触发）
```
startStatusPoll() (每1秒)
  → 查找所有 .steam-spinner 的元素（pending状态）
  → 如无 pending，跳过
  → 并行请求 store/search 数据
  → 只更新 pending 记录的状态图标（done→✓，error→✗）
```

### 记录渲染（增量 DOM 更新）
```
renderList(listId, items)
  → 已有元素：比较 outerHTML，仅在状态变化时更新 DOM
  → 新增元素：创建 DOM，按 index 插入到正确位置
  → 已消失元素：从列表移除
```

## 数据流

### API 接口
```
GET /stream?action=store&days=3    ← 获取近3天MCP写入记录
GET /stream?action=search&days=3  ← 获取近3天查询记录
```

### 返回数据格式
```json
{
  "items": [
    {
      "id": 1,
      "action": "store",
      "content": "记忆文本...",
      "status": "done",
      "memory_id": "xyz789",
      "created_at": "2026-04-30T14:30:25"
    }
  ],
  "total": 12
}
```

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：加载一次 + 启动2秒轮询 + 启动1秒状态轮询 |
| `cleanup()` | 清除 _streamTimer 和 _statusTimer |
| `loadStream()` | 并行获取 store/search 全量数据，渲染双栏 |
| `startStatusPoll()` | 1秒轮询，仅更新 pending 记录的状态图标 |
| `renderList(listId, items)` | 增量 DOM 更新（已有/新增/消失分类处理） |

## 全局状态
```javascript
var _streamTimer  = null;  // 主轮询定时器（2秒）
var _statusTimer = null;  // 状态轮询定时器（1秒）
```

## 视觉特效
- pending 状态：旋转 loading 图标
- done 状态：绿色 ✓
- error 状态：红色 ✗
- 绿点 = MCP 调用（store），蓝点 = 查询（search）

## 相关模块
- **Memory 模块**: 搜索/保存/整理记忆
- **MCP 服务**: brain_mcp 产生 store/search 调用记录

---

*最后更新: 2026-05-01*
