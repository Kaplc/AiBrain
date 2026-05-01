# 前端 - Memory 模块（记忆管理）

## 模块概述
记忆管理核心页面，三个Tab：搜索记忆（防抖搜索+历史）、保存记忆、整理记忆（去重分析+精炼合并）。整理状态持久化到window，切换页面不丢失。

## 文件位置
```
web/modules/memory/
├── memory.html   # HTML模板 + CSS（内联）
└── memory.js     # 页面逻辑
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
│  │ 相似度阈值: [0.85] [分析]                             ││
│  │ 分组卡片 + [精炼此组] → 精炼结果(可编辑) + [确认写入]  ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Tab 结构
| Tab | ID | 内容 |
|-----|----|------|
| 搜索 | `tabSearch` | 搜索框 + 结果列表 + 历史下拉 |
| 保存 | `tabStore` | 保存框 + 全部记忆列表 |
| 整理 | `tabOrganize` | 阈值输入 + 分析按钮 + 分组卡片 |

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
  → POST /search { query }
  → 渲染搜索结果（带相似度分数）
  → loadSearchHistory() 刷新历史

点击历史项 → searchFromHistory(query) → 填入搜索框 + 触发搜索
```

### 保存记忆
```
输入文本 → Ctrl+Enter 或 点击[保存记忆]
  → storeMemory()
    → POST /store { text }
    → 清空输入框
    → loadAll() 刷新列表
```

### 删除记忆
```
点击[✕] → deleteMemory(id)
  → POST /delete { memory_id: id }
  → 从本地数组移除
  → 刷新当前Tab的列表
```

### 记忆整理 - 完整流程
```
1. 选择阈值(0.90/0.85/0.80) → 点击[开始分析]
   → startOrganize()
     → POST /organize/dedup { similarity_threshold }
     → 返回 groups: [{ similarity, memories: [{id, text}] }]
     → 渲染分组卡片，每组一个[精炼此组]按钮

2. 点击[精炼此组] → refineGroup(groupIndex)
   → POST /organize/refine { groups: [该组数据] }
   → 返回 refined: [{ original_ids, refined_text, category, refined: bool }]
   → 在卡片内插入可编辑的精炼结果
   → 更新底部操作栏

3a. 单组确认 → applySingleRefine(refineIndex)
   → 读取可编辑区域的文本
   → POST /organize/apply { items: [{ delete_ids, new_text, category }] }
   → 标记该组为"已写入"

3b. 全部确认 → applyOrganize()
   → 收集所有勾选的精炼结果
   → POST /organize/apply { items: [...] }
   → 清空整理状态

4. [精炼剩余] → refineAllGroups()
   → 批量精炼所有未精炼的组
```

## 数据流

### API接口
| 操作 | 接口 | 说明 |
|------|------|------|
| 搜索 | `POST /search { query }` | 返回 `{ results: [{id, text, score, timestamp}] }` |
| 保存 | `POST /store { text }` | 返回 `{ result: "..." }` |
| 列表 | `POST /list {}` | 返回 `{ memories: [{id, text, timestamp}] }` |
| 删除 | `POST /delete { memory_id }` | 返回 `{ result: "..." }` |
| 计数 | `GET /memory-count` | 返回 `{ count: 1234 }` |
| 搜索历史 | `GET /search-history` | 返回 `{ history: [{query}] }` |
| 清空历史 | `DELETE /search-history` | 清空 |
| 去重分析 | `POST /organize/dedup { similarity_threshold }` | 返回 `{ groups, total_memories, grouped_count }` |
| 精炼 | `POST /organize/refine { groups }` | 返回 `{ refined: [{original_ids, refined_text, category}] }` |
| 写入 | `POST /organize/apply { items }` | 返回 `{ applied, deleted, added }` |

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：绑定事件、加载数据、恢复整理状态 |
| `switchTab(tab)` | 切换搜索/保存/整理Tab |
| `storeMemory()` | 保存新记忆 |
| `searchMemory()` | 搜索记忆 |
| `debounceSearch()` | 500ms防抖搜索 |
| `loadAll()` | 加载全部记忆 + 更新计数 |
| `deleteMemory(id)` | 删除单条记忆 |
| `renderList(items, isSearch, containerId)` | 渲染记忆卡片列表 |
| `startOrganize()` | 触发相似记忆分析 |
| `refineGroup(idx)` | 精炼单组记忆 |
| `refineAllGroups()` | 批量精炼所有未精炼的组 |
| `applySingleRefine(idx)` | 写入单组精炼结果 |
| `applyOrganize()` | 批量写入所有精炼结果 |
| `restoreOrganizeState()` | 页面切换回来时恢复整理状态 |
| `updateRefineFooter()` | 更新底部操作栏（已精炼 N/M 组 + 操作按钮） |
| `_saveOrganizeState()` | 同步状态到 window._organizeState（跨页面持久化） |

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

*最后更新: 2026-05-01*
