# 前端 - Steam 模块

## 模块概述
Steam（记忆流）模块实时显示系统活动记录，包括MCP调用和用户搜索操作，采用两栏对比布局，方便监控系统使用情况。

## 文件位置
```
web/modules/steam/
├── steam.html      # HTML模板
├── steam.js        # 主逻辑
└── steam.css       # 样式文件
```

## 功能特性

### 1. 实时活动监控
- **MCP调用记录**: 显示通过MCP协议存储的记忆
- **搜索操作记录**: 显示用户手动搜索的历史
- **实时更新**: 2秒轮询，自动加载新记录
- **时间筛选**: 支持查看最近3天的活动

### 2. 双栏对比布局
- **左侧栏**: MCP调用记录（蓝色主题）
- **右侧栏**: 搜索操作记录（绿色主题）
- **独立计数**: 每栏显示各自的记录数量
- **视觉区分**: 不同颜色标识不同类型的活动

### 3. 记录详情查看
- **内容预览**: 显示记录的主要内容
- **时间戳**: 精确到秒的操作时间
- **状态指示**: 显示操作状态（完成/错误）
- **操作来源**: 区分MCP调用和用户操作

### 4. 数据筛选功能
- **时间范围**: 默认显示最近3天记录
- **类型筛选**: 可单独查看MCP或搜索记录
- **状态筛选**: 按操作状态过滤记录
- **搜索过滤**: 在记录中搜索特定内容

## 界面布局

### 双栏布局设计
```html
<div class="steam-columns">
  <!-- 左侧：MCP调用记录 -->
  <div class="steam-column">
    <div class="steam-column-header">
      <div class="steam-column-dot store"></div>
      <span>MCP调用</span>
      <span class="steam-column-count" id="storeCount">0 条</span>
    </div>
    <div class="steam-list" id="storeList">
      <!-- MCP记录列表 -->
    </div>
  </div>

  <!-- 右侧：查询操作 -->
  <div class="steam-column">
    <div class="steam-column-header">
      <div class="steam-column-dot search"></div>
      <span>查询操作</span>
      <span class="steam-column-count" id="searchCount">0 条</span>
    </div>
    <div class="steam-list" id="searchList">
      <!-- 搜索记录列表 -->
    </div>
  </div>
</div>
```

### 记录项设计
```html
<div class="steam-item">
  <div class="steam-item-header">
    <div class="steam-item-time">19:30:45</div>
    <div class="steam-item-status done">完成</div>
  </div>
  <div class="steam-item-content">这是记忆内容...</div>
  <div class="steam-item-meta">
    <span class="steam-item-source">MCP</span>
    <span class="steam-item-id">ID: abc123</span>
  </div>
</div>
```

## API接口调用

### 获取活动流记录
```javascript
GET /stream?action=store&days=3
GET /stream?action=search&days=3
```
参数说明：
- `action`: 记录类型 (store/search)
- `days`: 查询天数 (默认3天)

返回数据格式：
```json
{
  "items": [
    {
      "id": "记录ID",
      "action": "操作类型",
      "content": "内容文本",
      "memory_id": "关联记忆ID",
      "created_at": "2026-04-29 19:30:45",
      "status": "done/error"
    }
  ],
  "total": 42
}
```

### 获取统计信息
```javascript
GET /stream/stats
```
返回各类型记录的数量统计。

## JavaScript核心逻辑

### 状态管理
```javascript
var _streamTimer = null;  // 轮询定时器
var lastUpdateTime = null; // 最后更新时间
var currentFilter = {      // 当前筛选条件
  days: 3,
  action: 'all',
  status: 'all'
};
```

### 初始化加载
```javascript
function onPageLoad() {
  loadStream();
  
  // 每 2 秒轮询新记录
  if (_streamTimer) clearInterval(_streamTimer);
  _streamTimer = setInterval(loadStream, 2000);
}

function cleanup() {
  if (_streamTimer) { 
    clearInterval(_streamTimer); 
    _streamTimer = null; 
  }
}
```

### 主加载函数
```javascript
async function loadStream() {
  try {
    // 并行获取 MCP 调用和搜索记录
    const [storeRes, searchRes] = await Promise.all([
      fetchJson(API + '/stream?action=store&days=' + currentFilter.days),
      fetchJson(API + '/stream?action=search&days=' + currentFilter.days),
    ]);

    const storeItems = storeRes.items || [];
    const searchItems = searchRes.items || [];
    const storeTotal = storeRes.total || 0;
    const searchTotal = searchRes.total || 0;

    // 更新总计数
    const countEl = document.getElementById('streamCount');
    if (countEl) countEl.textContent = `MCP ${storeTotal} 条 / 搜索 ${searchTotal} 条`;

    // 更新各栏计数
    const storeCountEl = document.getElementById('storeCount');
    const searchCountEl = document.getElementById('searchCount');
    if (storeCountEl) storeCountEl.textContent = `${storeItems.length} 条`;
    if (searchCountEl) searchCountEl.textContent = `${searchItems.length} 条`;

    // 渲染左侧：MCP调用
    renderList('storeList', storeItems, false);

    // 渲染右侧：查询操作
    renderList('searchList', searchItems, false);
    
    // 更新最后更新时间
    lastUpdateTime = new Date();
    
  } catch(e) { 
    console.error('[stream] load failed:', e); 
    showError('加载活动记录失败');
  }
}
```

### 列表渲染函数
```javascript
function renderList(listId, items, showDelete) {
  const listEl = document.getElementById(listId);
  if (!listEl) return;

  if (!items.length) {
    listEl.innerHTML = '<div class="steam-empty">暂无记录</div>';
    return;
  }

  const html = items.map(item => {
    const time = formatTime(item.created_at);
    const statusClass = item.status === 'error' ? 'error' : 'done';
    const statusText = item.status === 'error' ? '失败' : '完成';
    
    // 内容截断处理
    const content = item.content ? 
      truncateText(item.content, 120) : 
      '（无内容）';
    
    // 来源标识
    const source = item.action === 'store' ? 'MCP' : '搜索';
    
    return `
      <div class="steam-item">
        <div class="steam-item-header">
          <div class="steam-item-time">${time}</div>
          <div class="steam-item-status ${statusClass}">${statusText}</div>
        </div>
        <div class="steam-item-content">${escapeHtml(content)}</div>
        <div class="steam-item-meta">
          <span class="steam-item-source">${source}</span>
          ${item.memory_id ? `<span class="steam-item-id">ID: ${item.memory_id.slice(0, 8)}</span>` : ''}
        </div>
      </div>
    `;
  }).join('');

  listEl.innerHTML = html;
}
```

### 工具函数
```javascript
// 格式化时间显示
function formatTime(datetimeStr) {
  if (!datetimeStr) return '--:--:--';
  try {
    const dt = new Date(datetimeStr);
    return dt.toLocaleTimeString('zh-CN', { 
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return datetimeStr.slice(11, 19) || '--:--:--';
  }
}

// 文本截断
function truncateText(text, maxLength) {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

// 安全HTML转义
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
```

## 筛选功能实现

### 时间范围筛选
```javascript
function setTimeRange(days) {
  currentFilter.days = days;
  loadStream();
  
  // 更新按钮状态
  document.querySelectorAll('.time-range-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.days) === days);
  });
}
```

### 类型筛选
```javascript
function filterByType(type) {
  currentFilter.action = type;
  
  // 显示/隐藏对应的列
  const storeCol = document.querySelector('.steam-column:nth-child(1)');
  const searchCol = document.querySelector('.steam-column:nth-child(2)');
  
  if (type === 'store') {
    storeCol.style.display = 'block';
    searchCol.style.display = 'none';
  } else if (type === 'search') {
    storeCol.style.display = 'none';
    searchCol.style.display = 'block';
  } else {
    storeCol.style.display = 'block';
    searchCol.style.display = 'block';
  }
}
```

### 状态筛选
```javascript
function filterByStatus(status) {
  currentFilter.status = status;
  applyFilters();
}

function applyFilters() {
  // 重新加载数据并应用客户端筛选
  loadStream().then(() => {
    if (currentFilter.status !== 'all') {
      filterItemsByStatus(currentFilter.status);
    }
  });
}

function filterItemsByStatus(status) {
  // 在已加载的项目中筛选
  document.querySelectorAll('.steam-item').forEach(item => {
    const itemStatus = item.querySelector('.steam-item-status').textContent;
    const show = (status === 'all') || 
                 (status === 'done' && itemStatus === '完成') ||
                 (status === 'error' && itemStatus === '失败');
    item.style.display = show ? 'block' : 'none';
  });
}
```

## 样式设计要点

### 颜色主题
- **MCP列**: 蓝色主题 (#3b82f6)
  - 标题背景: #eff6ff
  - 圆点颜色: #3b82f6
  - 边框颜色: #dbeafe
  
- **搜索列**: 绿色主题 (#10b981)
  - 标题背景: #ecfdf5
  - 圆点颜色: #10b981
  - 边框颜色: #d1fae5

### 记录项样式
```css
.steam-item {
  background: white;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
  border-left: 3px solid;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}

.steam-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

/* MCP记录项 */
#storeList .steam-item {
  border-left-color: #3b82f6;
}

/* 搜索记录项 */
#searchList .steam-item {
  border-left-color: #10b981;
}
```

### 状态指示器
```css
.steam-item-status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.steam-item-status.done {
  background-color: #d1fae5;
  color: #065f46;
}

.steam-item-status.error {
  background-color: #fee2e2;
  color: #991b1b;
}

.steam-item-status.pending {
  background-color: #fef3c7;
  color: #92400e;
}
```

### 响应式设计
```css
/* 移动端：垂直堆叠 */
@media (max-width: 768px) {
  .steam-columns {
    flex-direction: column;
  }
  
  .steam-column {
    width: 100%;
    margin-bottom: 20px;
  }
}

/* 平板端：两列并排 */
@media (min-width: 769px) and (max-width: 1024px) {
  .steam-columns {
    flex-wrap: wrap;
  }
  
  .steam-column {
    width: 48%;
    margin-bottom: 20px;
  }
}

/* 桌面端：标准两栏 */
@media (min-width: 1025px) {
  .steam-columns {
    display: flex;
    gap: 20px;
  }
  
  .steam-column {
    flex: 1;
  }
}
```

## 性能优化

### 轮询优化
```javascript
// 智能轮询：当页面不可见时暂停轮询
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (_streamTimer) {
      clearInterval(_streamTimer);
      _streamTimer = null;
    }
  } else {
    if (!_streamTimer) {
      loadStream(); // 立即加载一次
      _streamTimer = setInterval(loadStream, 2000);
    }
  }
});
```

### 数据去重
```javascript
// 避免重复显示相同记录
const seenIds = new Set();

function filterNewItems(items) {
  const newItems = [];
  
  for (const item of items) {
    if (!seenIds.has(item.id)) {
      seenIds.add(item.id);
      newItems.push(item);
      
      // 限制缓存大小
      if (seenIds.size > 1000) {
        const idsArray = Array.from(seenIds);
        seenIds.clear();
        // 保留最近500个ID
        idsArray.slice(-500).forEach(id => seenIds.add(id));
      }
    }
  }
  
  return newItems;
}
```

### 批量更新
```javascript
// 使用requestAnimationFrame优化渲染
let renderPending = false;

function scheduleRender() {
  if (!renderPending) {
    renderPending = true;
    requestAnimationFrame(() => {
      renderLists();
      renderPending = false;
    });
  }
}
```

## 错误处理

### 网络错误处理
```javascript
async function fetchJson(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Fetch failed for ${url}:`, error);
    return { items: [], total: 0 };
  }
}
```

### 数据验证
```javascript
function validateStreamItem(item) {
  const requiredFields = ['id', 'action', 'created_at'];
  const validActions = ['store', 'search'];
  const validStatuses = ['done', 'error', 'pending'];
  
  // 检查必填字段
  for (const field of requiredFields) {
    if (!item[field]) {
      console.warn('Stream item missing required field:', field, item);
      return false;
    }
  }
  
  // 检查action有效性
  if (!validActions.includes(item.action)) {
    console.warn('Invalid action in stream item:', item.action, item);
    return false;
  }
  
  // 检查status有效性
  if (item.status && !validStatuses.includes(item.status)) {
    console.warn('Invalid status in stream item:', item.status, item);
    return false;
  }
  
  return true;
}
```

## 扩展性设计

### 添加新记录类型
```javascript
// 扩展支持新的记录类型
const recordTypes = {
  store: { 
    name: 'MCP调用', 
    color: '#3b82f6',
    icon: '🔧'
  },
  search: { 
    name: '搜索操作', 
    color: '#10b981',
    icon: '🔍'
  },
  organize: { 
    name: '整理操作', 
    color: '#8b5cf6',
    icon: '🗂️'
  }
};

function registerRecordType(type, config) {
  recordTypes[type] = config;
}
```

### 自定义渲染器
```javascript
// 支持自定义记录渲染
const itemRenderers = {
  default: renderDefaultItem,
  store: renderStoreItem,
  search: renderSearchItem
};

function registerItemRenderer(type, renderer) {
  itemRenderers[type] = renderer;
}

function renderItem(item) {
  const renderer = itemRenderers[item.action] || itemRenderers.default;
  return renderer(item);
}
```

## 相关模块
- **Memory模块**: 产生MCP调用和搜索记录
- **Overview模块**: 显示系统状态概览
- **Settings模块**: 配置活动流相关设置

---

*最后更新: 2026-04-29*