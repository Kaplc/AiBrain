# 前端 - Memory 模块（记忆管理）

## 模块概述
记忆管理核心页面，三个Tab：搜索记忆（防抖搜索+历史）、保存记忆、整理记忆（流式去重分析+暂停控制+精炼合并）。整理状态持久化到window，切换页面不丢失。

## 文件位置
```
web/src/views/MemoryView/
├── MemoryView.vue    # Vue组件，HTML模板 + CSS（内联）
├── SearchTab.ts      # 搜索Tab逻辑（防抖搜索 + 历史）
├── OrganizeTab.ts    # 整理Tab逻辑（流式分析 + 暂停/恢复/停止）
└── StoreTab.ts       # 保存Tab逻辑
```

## 界面布局
```
┌──────────────────────────────────────────────────────────┐
│ 记忆                            记忆总数: 1234   ↻       │  ← header + 总数
├──────────────────────────────────────────────────────────┤
│  [搜索]  [保存]  [整理]                                    │  ← Tab 导航
├──────────────────────────────────────────────────────────┤
│                                                          │
│  搜索标签                                                 │
│  ┌──────────────────────────────────────────────────────┐│
│  │ 🔍 搜索记忆...                                [🕐历史]││
│  └──────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────┐│
│  │ 记忆卡片列表（搜索结果/全部记忆）                      ││
│  │ 搜索中显示loading spinner                             ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  保存标签                                                │
│  ┌──────────────────────────────────────────────────────┐│
│  │ [textarea 保存记忆内容 - Ctrl+Enter 保存]             ││
│  └──────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────┐│
│  │ 全部记忆列表                                          ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  整理标签                                                │
│  ┌──────────────────────────────────────────────────────┐│
│  │ 相似度阈值: [0.90/0.85/0.80]                         ││
│  │ [开始分析] → 分析中:[暂停][继续][停止]                 ││
│  │ 流式加载分组卡片                                      ││
│  │ 分组卡片 + [精炼此组] → 精炼结果(可编辑) + [确认写入]  ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Tab 结构
| Tab | ID | 内容 |
|-----|----|------|
| 搜索 | `tabSearch` | 搜索框 + 结果列表 + 历史下拉，搜索中禁用重复提交 |
| 保存 | `tabStore` | 保存框 + 全部记忆列表 |
| 整理 | `tabOrganize` | 流式分析（暂停/恢复/停止）+ 分组卡片 + 精炼合并 |

### 整理Tab按钮状态
| 状态 | 显示按钮 |
|------|---------|
| 空闲 | `[开始分析]`（主色） |
| 分析中 | `[暂停分析]`（警告色）+ `[停止]`（红色小按钮） |
| 已暂停 | `[继续分析]`（主色）+ `[停止]`（红色小按钮） |

## 交互逻辑流

### 页面加载
```
onPageLoad()
  ├── 绑定搜索框回车事件
  ├── 绑定保存框 Ctrl+Enter 事件
  ├── loadAll()              ← 加载全部记忆 + 更新计数
  ├── loadSearchHistory()    ← 加载搜索历史
  └── restoreOrganizeState() ← 恢复整理状态（从window）
```

### 搜索记忆
```
输入框 oninput → debounceSearch() → 500ms后 → searchMemory()
  → POST /memory/search { query }
  → 渲染搜索结果（带相似度分数）
  → loadSearchHistory() 刷新历史

点击历史项 → searchFromHistory(query) → 填入搜索框 + 触发搜索
```

### 保存记忆
```
输入文本 → Ctrl+Enter 或 点击[保存记忆]
  → storeMemory()
    → POST /memory/store { text }
    → 清空输入框
    → loadAll() 刷新列表
```

### 删除记忆
```
点击[✕] → deleteMemory(id)
  → POST /memory/delete { memory_id: id }
  → 从本地数组移除
  → 刷新当前Tab的列表
```

### 记忆整理 - 流式分析完整流程
```
1. 选择阈值(0.90/0.85/0.80) → 点击[开始分析]
   → OrganizeTab.start()
     → POST /memory/organize/dedup/stream (SSE流式)
     → 实时接收 batch/done/stopped/error 消息
     → 流式追加 groups 到 this.groups.value
     → 禁止重复提交（isSearching 防抖保护 + busy 状态）

2. 分析中点击[暂停分析]
   → OrganizeTab.pause()
     → POST /memory/organize/dedup/pause
     → 设置 paused.value = true

3. 已暂停点击[继续分析]
   → OrganizeTab.resume()
     → POST /memory/organize/dedup/resume
     → paused.value = false

4. 分析中点击[停止]
   → OrganizeTab.stop()
     → abortController.abort() + POST /memory/organize/dedup/stop
     → busy.value = false, paused.value = false

5. 分析完成/停止后
   → 显示分组卡片
   → 每组一个[精炼此组]按钮

6. 点击[精炼此组] → refineGroup(groupIndex)
   → POST /memory/organize/refine { groups: [该组数据] }
   → 返回 refined: [{ original_ids, refined_text, category, refined: bool }]
   → 在卡片内插入可编辑的精炼结果
   → 更新底部操作栏

7a. 单组确认 → applySingleRefine(refineIndex)
   → 读取可编辑区域的文本
   → POST /memory/organize/apply { items: [{ delete_ids, new_text, category }] }
   → 标记该组为"已写入"

7b. 全部确认 → applyOrganize()
   → 收集所有勾选的精炼结果
   → POST /memory/organize/apply { items: [...] }
   → 清空整理状态

8. [精炼剩余] → refineAllGroups()
   → 批量精炼所有未精炼的组
```

### SSE 流式消息格式
```javascript
// 定期推送已发现的组
{ "type": "batch", "found": 5, "total": 100, "groups": [...] }

// 分析完成
{ "type": "done", "total": 100, "grouped": 30, "ungrouped": 70, "groups": [...] }

// 中途停止
{ "type": "stopped", "found": 12, "groups": [...] }

// 异常
{ "type": "error", "error": "错误信息" }
```

## 数据流

### API接口
| 操作 | 接口 | 代码位置 | 说明 |
|------|------|---------|------|
| 搜索 | `POST /memory/search { query }` | `memory_routes.py:33` | 返回 `{ results: [...] }`，防重复提交 |
| 保存 | `POST /memory/store { text }` | `memory_routes.py:16` | 返回 `{ result: "..." }` |
| 列表 | `POST /memory/list { offset, limit }` | `memory_routes.py:88` | 返回 `{ memories: [...] }` |
| 删除 | `POST /memory/delete { memory_id }` | `memory_routes.py:103` | 返回 `{ result: "..." }` |
| 计数 | `GET /memory/count` | `memory_routes.py:149` | 返回 `{ count: N }` |
| 搜索历史 | `GET /memory/search-history` | `memory_routes.py:155` | 返回 `{ history: [...] }` |
| 清空历史 | `DELETE /memory/search-history` | `memory_routes.py:164` | 返回 `{ ok: true }` |
| 流式去重分析 | `POST /memory/organize/dedup/stream` | `memory_routes.py:198` | **SSE流式**，实时推送 batch/done/stopped/error |
| 暂停分析 | `POST /memory/organize/dedup/pause` | `memory_routes.py:229` | 暂停去重分析（可恢复） |
| 恢复分析 | `POST /memory/organize/dedup/resume` | `memory_routes.py:236` | 继续去重分析 |
| 停止分析 | `POST /memory/organize/dedup/stop` | `memory_routes.py:243` | 终止去重分析（不可恢复） |
| 精炼 | `POST /memory/organize/refine { groups }` | `memory_routes.py:251` | 返回 `{ refined: [...] }` |
| 写入 | `POST /memory/organize/apply { items }` | `memory_routes.py:271` | 返回 `{ applied, deleted, added }` |

**注意**：所有接口前缀已从 `/` 变更为 `/memory/`（2026-05-04）

## 核心函数（按文件分类）

### MemoryView.vue
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：绑定事件、加载数据、恢复整理状态 |
| `switchTab(tab)` | 切换搜索/保存/整理Tab |
| `storeMemory()` | 保存新记忆 |
| `searchMemory()` | 搜索记忆 |
| `debounceSearch()` | 500ms防抖搜索，isSearching 防重复 |
| `loadAll()` | 加载全部记忆 + 更新计数 |
| `deleteMemory(id)` | 删除单条记忆 |
| `renderList(items, isSearch, containerId)` | 渲染记忆卡片列表 |

### SearchTab.ts
| 方法 | 说明 |
|------|------|
| `debounceSearch()` | 500ms防抖，isSearching 防重复提交 |
| `search()` | POST /memory/search，渲染结果 |
| `searchFromHistory(q)` | 从历史项触发搜索 |

### OrganizeTab.ts
| 方法 | 说明 | 代码位置 |
|------|------|---------|
| `start()` | SSE 流式去重分析，重置状态 | `OrganizeTab.ts:27` |
| `pause()` | POST /memory/organize/dedup/pause | `OrganizeTab.ts:114` |
| `resume()` | POST /memory/organize/dedup/resume | `OrganizeTab.ts:124` |
| `stop()` | abort + POST /memory/organize/dedup/stop | `OrganizeTab.ts:134` |
| `refineGroup(idx)` | POST /memory/organize/refine | `OrganizeTab.ts:146` |
| `applySingle(groupId)` | POST /memory/organize/apply | `OrganizeTab.ts:176` |
| `applyAll()` | 批量写入所有精炼结果 | `OrganizeTab.ts:202` |

### StoreTab.ts
| 方法 | 说明 |
|------|------|
| `store()` | POST /memory/store 保存记忆 |
| `loadAll()` | 加载全部记忆列表 |

## SearchTab 状态
```typescript
readonly isSearching = ref(false)  // 防止防抖期间重复提交
```

## OrganizeTab 状态
```typescript
readonly groups = ref<OrganizeGroup[]>([])     // 流式追加的分组
readonly refined = ref<RefinedItem[]>([])       // 精炼结果
readonly busy = ref(false)                      // 分析中
readonly paused = ref(false)                   // 已暂停
readonly appliedIds = ref<number[]>([])         // 已写入的ID
readonly threshold = ref('0.85')               // 相似度阈值
private _abortController: AbortController | null = null  // SSE中止控制器
```

### OrganizeTab 流式方法
| 方法 | 说明 |
|------|------|
| `start()` | 启动 SSE 流式去重分析，重置状态 |
| `pause()` | POST /organize/dedup/pause，暂停批处理 |
| `resume()` | POST /organize/dedup/resume，恢复批处理 |
| `stop()` | abort + POST /organize/dedup/stop，终止分析 |

## 全局状态
```javascript
var allMemories = [];       // 全部记忆
var searchResults = [];     // 搜索结果
var activeQuery = '';       // 当前搜索词
var searchHistory = [];     // 搜索历史
var currentTab = 'search';  // 当前Tab

// 整理状态（持久化到window，跨页面保持）
window._organizeState = {
  groups: [],              // 去重分组
  refined: [],             // 精炼结果
  busy: false,             // 是否正在分析
  appliedGroups: []        // 已写入的组索引
};
```

## 整理状态持久化
整理状态保存在 `window._organizeState` 中，页面切换后自动恢复：
- `groups`：分组数据
- `refined`：精炼结果
- `busy`：分析中标志
- `appliedGroups`：已写入的组索引

---

*最后更新: 2026-05-04*
