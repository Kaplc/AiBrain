# 前端 - Memory 模块

## 模块概述
Memory（记忆）模块是AiBrain的核心功能界面，提供记忆的搜索、存储、整理和管理功能。支持语义搜索、批量操作和智能整理。

## 文件位置
```
web/modules/memory/
├── memory.html      # HTML模板
├── memory.js        # 主逻辑
└── memory.css       # 样式文件
```

## 功能特性

### 1. 记忆搜索功能
- **语义搜索**: 基于BGE-M3向量的语义匹配
- **实时搜索**: 输入时自动触发搜索（防抖）
- **搜索结果**: 显示匹配度和相关记忆
- **搜索历史**: 记录用户搜索关键词

### 2. 记忆存储功能
- **文本输入**: 支持多行文本输入
- **快速存储**: Ctrl+Enter快速保存
- **批量导入**: 支持批量文本导入
- **存储确认**: 显示存储成功反馈

### 3. 记忆整理功能
- **自动分类**: 基于语义相似度自动分组
- **手动调整**: 支持手动合并和拆分组
- **标签应用**: 为分组添加描述性标签
- **批量写入**: 将整理结果保存到记忆库

### 4. 记忆管理功能
- **全部记忆**: 查看所有记忆列表
- **分页浏览**: 支持分页加载
- **记忆详情**: 查看单条记忆详情
- **删除功能**: 支持删除不需要的记忆

## 界面布局

### 标签页设计
```html
<div class="nav-tabs">
  <button class="nav-tab active" data-tab="search" onclick="switchTab('search')">搜索记忆</button>
  <button class="nav-tab" data-tab="store" onclick="switchTab('store')">保存记忆</button>
  <button class="nav-tab" data-tab="organize" onclick="switchTab('organize')">整理记忆</button>
  <button class="nav-tab" data-tab="all" onclick="switchTab('all')">全部记忆</button>
</div>
```

### 搜索界面
- **搜索输入框**: 带实时搜索提示
- **搜索按钮**: 手动触发搜索
- **结果列表**: 显示匹配的记忆项
- **匹配度显示**: 用百分比表示相关性

### 存储界面
- **多行文本域**: 支持长篇文本
- **字符计数**: 显示输入字符数
- **存储按钮**: 提交保存
- **历史记录**: 最近存储的记录

### 整理界面
- **分组区域**: 显示自动生成的记忆组
- **组操作**: 合并、拆分、重命名
- **预览区域**: 显示组内记忆内容
- **应用按钮**: 将整理结果写入系统

## API接口调用

### 搜索记忆
```javascript
POST /search
{
  "query": "搜索关键词"
}
```
返回搜索结果列表，包含：
- `id`: 记忆ID
- `text`: 记忆文本
- `score`: 匹配分数（0-1）
- `metadata`: 附加信息

### 存储记忆
```javascript
POST /store
{
  "text": "要存储的记忆文本"
}
```
返回存储结果：
- `ok`: 操作状态
- `id`: 新记忆的ID
- `message`: 状态信息

### 获取所有记忆
```javascript
POST /list
{
  "page": 1,
  "pageSize": 20
}
```
返回分页的记忆列表。

### 整理记忆
```javascript
POST /organize
{
  "action": "group"/"refine"/"apply"
}
```
返回整理结果。

### 删除记忆
```javascript
POST /delete
{
  "id": "记忆ID"
}
```
返回删除状态。

## JavaScript核心逻辑

### 状态管理
```javascript
// 全局状态变量
var allMemories = [];          // 所有记忆列表
var searchResults = [];        // 搜索结果
var searchTimer = null;        // 防抖定时器
var activeQuery = '';          // 当前搜索词
var searchHistory = [];        // 搜索历史
var currentTab = 'search';     // 当前标签页

// 整理状态持久化
window._organizeState = window._organizeState || { 
  groups: [], 
  refined: [], 
  busy: false, 
  appliedGroups: [] 
};
```

### 防抖搜索实现
```javascript
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const query = document.getElementById('searchInput').value.trim();
    if (query && query !== activeQuery) {
      searchMemory(query);
    }
  }, 300);
}
```

### 搜索功能
```javascript
async function searchMemory(query = null) {
  if (!query) query = document.getElementById('searchInput').value.trim();
  if (!query) return;
  
  activeQuery = query;
  
  try {
    const res = await fetch(`${API}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    
    const data = await res.json();
    searchResults = data.results || [];
    renderSearchResults();
    
    // 记录搜索历史（非MCP来源）
    if (data.results && data.results.length > 0) {
      addToSearchHistory(query);
    }
  } catch (error) {
    console.error('搜索失败:', error);
    showError('搜索失败，请检查网络连接');
  }
}
```

### 存储功能
```javascript
async function storeMemory() {
  const text = document.getElementById('storeInput').value.trim();
  if (!text) {
    showError('请输入要保存的内容');
    return;
  }
  
  try {
    const res = await fetch(`${API}/store`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    
    const data = await res.json();
    if (data.ok) {
      showSuccess('记忆保存成功');
      document.getElementById('storeInput').value = '';
      // 更新记忆总数
      fetchMemoryCount();
    } else {
      showError(data.error || '保存失败');
    }
  } catch (error) {
    console.error('保存失败:', error);
    showError('保存失败，请检查网络连接');
  }
}
```

### 整理功能
```javascript
async function organizeMemories() {
  if (_organizeBusy) return;
  _organizeBusy = true;
  
  try {
    // 1. 获取所有记忆
    const all = await fetchAllMemories();
    
    // 2. 调用整理API
    const res = await fetch(`${API}/organize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        action: 'group',
        memories: all 
      })
    });
    
    const data = await res.json();
    organizeGroups = data.groups || [];
    organizeRefined = data.refined || [];
    
    // 3. 渲染整理界面
    renderOrganizeView();
    
  } catch (error) {
    console.error('整理失败:', error);
    showError('记忆整理失败');
  } finally {
    _organizeBusy = false;
  }
}
```

## 数据渲染

### 搜索结果渲染
```javascript
function renderSearchResults() {
  const container = document.getElementById('searchResults');
  if (!container) return;
  
  if (searchResults.length === 0) {
    container.innerHTML = '<div class="empty-state">未找到相关记忆</div>';
    return;
  }
  
  const html = searchResults.map(item => `
    <div class="memory-item">
      <div class="memory-score">${Math.round(item.score * 100)}%</div>
      <div class="memory-content">${escapeHtml(item.text)}</div>
      <div class="memory-actions">
        <button class="btn-icon" onclick="copyMemory('${item.id}')" title="复制">📋</button>
        <button class="btn-icon" onclick="deleteMemory('${item.id}')" title="删除">🗑️</button>
      </div>
    </div>
  `).join('');
  
  container.innerHTML = html;
}
```

### 记忆列表渲染
```javascript
function renderMemoryList(memories, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  if (memories.length === 0) {
    container.innerHTML = '<div class="empty-state">暂无记忆</div>';
    return;
  }
  
  // 分页渲染逻辑
  const page = currentPage[containerId] || 1;
  const pageSize = 20;
  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  const pageMemories = memories.slice(start, end);
  
  const html = pageMemories.map((item, index) => `
    <div class="memory-list-item" data-id="${item.id}">
      <div class="list-index">${start + index + 1}</div>
      <div class="list-content">${truncateText(item.text, 200)}</div>
      <div class="list-actions">
        <button class="btn-icon" onclick="viewMemoryDetail('${item.id}')" title="查看详情">👁️</button>
        <button class="btn-icon" onclick="deleteMemory('${item.id}')" title="删除">🗑️</button>
      </div>
    </div>
  `).join('');
  
  container.innerHTML = html;
  
  // 渲染分页控件
  renderPagination(containerId, memories.length, pageSize, page);
}
```

## 样式设计要点

### 标签页样式
- **激活状态**: 蓝色边框和文字
- **悬停效果**: 轻微背景色变化
- **过渡动画**: 平滑的切换效果

### 记忆项样式
- **卡片设计**: 圆角阴影卡片
- **分数显示**: 右侧彩色百分比
- **操作按钮**: 悬停显示操作按钮

### 响应式设计
- **移动端**: 垂直排列，简化操作
- **平板端**: 两列布局
- **桌面端**: 充分利用空间的多列布局

## 状态管理

### 标签页状态
```javascript
function switchTab(tabName) {
  // 更新标签页状态
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });
  
  // 显示对应面板
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.style.display = panel.id === `tab${capitalize(tabName)}` ? 'block' : 'none';
  });
  
  currentTab = tabName;
  
  // 加载对应数据
  if (tabName === 'all') {
    loadAllMemories();
  } else if (tabName === 'organize') {
    loadOrganizeView();
  }
}
```

### 搜索状态
- **输入中**: 显示加载指示器
- **搜索中**: 显示搜索进度
- **有结果**: 显示结果数量和列表
- **无结果**: 显示空状态提示

## 性能优化

### 虚拟滚动
对于大量记忆列表，实现虚拟滚动：
```javascript
// 只渲染可见区域的记忆项
function setupVirtualScroll(containerId, items) {
  const container = document.getElementById(containerId);
  const viewportHeight = container.clientHeight;
  const itemHeight = 60;
  
  container.addEventListener('scroll', () => {
    const scrollTop = container.scrollTop;
    const startIndex = Math.floor(scrollTop / itemHeight);
    const endIndex = Math.min(startIndex + Math.ceil(viewportHeight / itemHeight), items.length);
    
    renderVisibleItems(items.slice(startIndex, endIndex), startIndex);
  });
}
```

### 记忆缓存
```javascript
// 缓存已加载的记忆
const memoryCache = new Map();

async function getMemory(id) {
  if (memoryCache.has(id)) {
    return memoryCache.get(id);
  }
  
  const memory = await fetchMemoryById(id);
  memoryCache.set(id, memory);
  return memory;
}
```

## 错误处理

### 网络错误
```javascript
function handleNetworkError(error) {
  console.error('网络错误:', error);
  showError('网络连接失败，请检查网络状态');
  
  // 重试逻辑
  if (error.retryCount < 3) {
    setTimeout(() => {
      retryOperation(error.operation, error.retryCount + 1);
    }, 1000 * Math.pow(2, error.retryCount));
  }
}
```

### API错误
```javascript
async function callApi(endpoint, data) {
  try {
    const res = await fetch(`${API}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    
    if (!res.ok) {
      throw new Error(`API错误: ${res.status} ${res.statusText}`);
    }
    
    return await res.json();
  } catch (error) {
    handleApiError(error, endpoint, data);
    throw error;
  }
}
```

## 扩展性设计

### 插件系统
```javascript
// 记忆操作插件接口
window.memoryPlugins = window.memoryPlugins || [];

function registerMemoryPlugin(plugin) {
  window.memoryPlugins.push(plugin);
}

// 在记忆项渲染时调用插件
function renderMemoryWithPlugins(memory) {
  const baseHtml = renderMemoryBase(memory);
  const pluginHtml = window.memoryPlugins.map(plugin => 
    plugin.render(memory)
  ).join('');
  
  return baseHtml + pluginHtml;
}
```

### 自定义视图
支持自定义记忆显示模板：
```javascript
// 配置记忆显示模板
const memoryTemplates = {
  default: (memory) => `<div>${memory.text}</div>`,
  detailed: (memory) => `
    <div class="memory-detailed">
      <div class="memory-text">${memory.text}</div>
      <div class="memory-meta">
        <span>${formatDate(memory.created_at)}</span>
        <span>分数: ${memory.score || 'N/A'}</span>
      </div>
    </div>
  `
};
```

## 相关模块
- **Overview模块**: 显示记忆统计信息
- **Stream模块**: 记录记忆操作历史
- **Settings模块**: 配置记忆相关设置

---

*最后更新: 2026-04-29*