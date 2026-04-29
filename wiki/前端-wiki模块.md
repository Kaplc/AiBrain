# 前端 - Wiki 模块

## 模块概述
Wiki模块提供知识库管理功能，集成LightRAG引擎，支持文档搜索、索引管理和知识图谱可视化，是AiBrain的知识管理核心。

## 文件位置
```
web/modules/wiki/
├── wiki.html      # HTML模板
├── wiki.js        # 主逻辑
└── wiki.css       # 样式文件
```

## 功能特性

### 1. 知识库搜索
- **多模式搜索**: 支持naive/local/global/hybrid/mix五种搜索模式
- **语义搜索**: 基于LightRAG的知识图谱增强检索
- **实时结果**: 即时显示搜索结果和相关性
- **搜索历史**: 记录用户搜索历史

### 2. 文档管理
- **文档列表**: 显示wiki目录下的所有Markdown文件
- **文件统计**: 显示文件数量、总大小、最近更新
- **文档预览**: 支持Markdown文档实时预览
- **文件操作**: 打开、编辑、删除文档

### 3. 索引管理
- **索引状态**: 显示LightRAG索引构建状态
- **重建索引**: 手动触发全量索引重建
- **增量同步**: 自动检测文件变化并更新索引
- **索引统计**: 显示实体图、社区图规模

### 4. 知识图谱可视化
- **实体关系图**: 可视化文档内的实体关系
- **社区关联图**: 显示跨文档的宏观关联
- **交互探索**: 支持点击节点展开关联
- **图布局控制**: 多种布局算法选择

## 界面布局

### 主界面结构
```html
<div class="wiki-wrap">
  <!-- 头部区域 -->
  <div class="wiki-header">
    <div class="wiki-title">Wiki 知识库</div>
    <button class="btn-settings" onclick="openWikiSettings()">⚙️ 设置</button>
  </div>

  <!-- 统计卡片 -->
  <div class="wiki-row">
    <div class="wscard">
      <div class="wsc-label">文件数</div>
      <div class="wsc-value" id="wikiFileCount">-</div>
    </div>
    <div class="wscard">
      <div class="wsc-label">总大小</div>
      <div class="wsc-value" id="wikiTotalSize">-</div>
      <div class="wsc-sub" id="wikiSizeSub"></div>
    </div>
    <div class="wscard">
      <div class="wsc-label">状态</div>
      <div class="wsc-value" id="wikiStatus" style="font-size:15px;color:#86efac">就绪</div>
    </div>
  </div>

  <!-- 搜索区域 -->
  <div class="wiki-search">
    <input type="text" id="wikiSearchInput" placeholder="搜索知识库..." />
    <select id="wikiSearchMode">
      <option value="naive">快速搜索</option>
      <option value="local">本地图搜索</option>
      <option value="global">社区图搜索</option>
      <option value="hybrid">混合搜索</option>
      <option value="mix">融合搜索</option>
    </select>
    <button class="btn btn-primary" onclick="wikiSearch()">搜索</button>
  </div>

  <!-- 结果/文档区域 -->
  <div class="wiki-content">
    <div class="wiki-tabs">
      <button class="wiki-tab active" data-tab="results">搜索结果</button>
      <button class="wiki-tab" data-tab="files">文档列表</button>
      <button class="wiki-tab" data-tab="graph">知识图谱</button>
    </div>
    
    <div id="wikiResults" class="tab-content active">
      <!-- 搜索结果 -->
    </div>
    
    <div id="wikiFiles" class="tab-content">
      <!-- 文档列表 -->
    </div>
    
    <div id="wikiGraph" class="tab-content">
      <!-- 知识图谱 -->
    </div>
  </div>
</div>
```

## API接口调用

### 知识库搜索
```javascript
POST /wiki/search
{
  "query": "搜索关键词",
  "mode": "naive"  // naive/local/global/hybrid/mix
}
```
返回搜索结果，包含：
- `results`: 搜索结果列表
- `mode`: 使用的搜索模式
- `time_cost`: 搜索耗时（秒）
- `graph_info`: 图谱信息（如使用）

### 获取文档列表
```javascript
GET /wiki/list
```
返回wiki目录下的文件列表：
- `files`: 文件信息数组
- `total_count`: 文件总数
- `total_size`: 总文件大小（字节）
- `last_updated`: 最后更新时间

### 索引管理
```javascript
POST /wiki/index
```
触发索引重建，返回：
- `added`: 新增文件列表
- `updated`: 更新文件列表
- `deleted`: 删除文件列表
- `unchanged`: 未变化文件数
- `errors`: 错误信息列表

### 获取索引状态
```javascript
GET /wiki/status
```
返回索引状态信息：
- `indexed`: 是否已建立索引
- `file_count`: 索引文件数
- `entity_count`: 实体数量
- `community_count`: 社区数量
- `last_build`: 最后构建时间

### 获取文档内容
```javascript
GET /wiki/file?path=文档路径
```
返回指定文档的Markdown内容。

## JavaScript核心逻辑

### 状态管理
```javascript
// Wiki模块全局状态
var wikiState = {
  currentTab: 'results',
  searchMode: 'naive',
  searchResults: [],
  fileList: [],
  graphData: null,
  isLoading: false,
  lastSearch: null
};

// 搜索模式配置
const searchModes = {
  naive: { name: '快速搜索', desc: '纯向量匹配，约0.2秒' },
  local: { name: '本地图搜索', desc: '实体图增强，约15秒' },
  global: { name: '社区图搜索', desc: '社区图增强，约15秒' },
  hybrid: { name: '混合搜索', desc: 'LLM+图+向量，约30-45秒' },
  mix: { name: '融合搜索', desc: '多策略融合，约20秒' }
};
```

### 初始化加载
```javascript
function onPageLoad() {
  // 加载统计信息
  loadWikiStats();
  
  // 加载文档列表
  loadFileList();
  
  // 加载索引状态
  loadIndexStatus();
  
  // 设置搜索框回车事件
  document.getElementById('wikiSearchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') wikiSearch();
  });
  
  // 设置标签页切换
  setupTabSwitching();
  
  // 初始加载知识图谱（延迟加载）
  setTimeout(() => {
    if (wikiState.currentTab === 'graph') {
      loadKnowledgeGraph();
    }
  }, 1000);
}
```

### 搜索功能
```javascript
async function wikiSearch() {
  const query = document.getElementById('wikiSearchInput').value.trim();
  const mode = document.getElementById('wikiSearchMode').value;
  
  if (!query) {
    showError('请输入搜索关键词');
    return;
  }
  
  if (wikiState.isLoading) {
    showWarning('正在搜索中，请稍候...');
    return;
  }
  
  wikiState.isLoading = true;
  wikiState.lastSearch = { query, mode, time: new Date() };
  
  try {
    // 显示加载状态
    setLoadingState(true);
    
    const response = await fetch(`${API}/wiki/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, mode })
    });
    
    const data = await response.json();
    
    if (data.error) {
      throw new Error(data.error);
    }
    
    wikiState.searchResults = data.results || [];
    
    // 渲染搜索结果
    renderSearchResults(data);
    
    // 记录搜索历史
    addToSearchHistory(query, mode, data.results.length);
    
    // 切换到结果标签页
    switchTab('results');
    
  } catch (error) {
    console.error('Wiki搜索失败:', error);
    showError(`搜索失败: ${error.message}`);
  } finally {
    wikiState.isLoading = false;
    setLoadingState(false);
  }
}
```

### 文档列表加载
```javascript
async function loadFileList() {
  try {
    const response = await fetch(`${API}/wiki/list`);
    const data = await response.json();
    
    wikiState.fileList = data.files || [];
    
    // 更新统计信息
    document.getElementById('wikiFileCount').textContent = data.total_count || 0;
    document.getElementById('wikiTotalSize').textContent = formatFileSize(data.total_size);
    
    // 渲染文件列表
    renderFileList();
    
  } catch (error) {
    console.error('加载文档列表失败:', error);
    showError('加载文档列表失败');
  }
}
```

### 索引管理
```javascript
async function rebuildIndex() {
  if (wikiState.isLoading) {
    showWarning('正在执行其他操作，请稍候...');
    return;
  }
  
  const confirmed = confirm('重建索引可能需要几分钟，确认继续吗？');
  if (!confirmed) return;
  
  wikiState.isLoading = true;
  
  try {
    showInfo('开始重建索引，请稍候...');
    
    const response = await fetch(`${API}/wiki/index`, {
      method: 'POST'
    });
    
    const data = await response.json();
    
    if (data.error) {
      throw new Error(data.error);
    }
    
    // 显示重建结果
    showIndexRebuildResult(data);
    
    // 重新加载状态和列表
    loadWikiStats();
    loadFileList();
    loadIndexStatus();
    
  } catch (error) {
    console.error('重建索引失败:', error);
    showError(`重建索引失败: ${error.message}`);
  } finally {
    wikiState.isLoading = false;
  }
}

function showIndexRebuildResult(result) {
  const message = `
索引重建完成：
- 新增文件: ${result.added?.length || 0} 个
- 更新文件: ${result.updated?.length || 0} 个  
- 删除文件: ${result.deleted?.length || 0} 个
- 未变化文件: ${result.unchanged || 0} 个
${result.errors?.length ? `- 错误: ${result.errors.length} 个` : ''}
  `.trim();
  
  showSuccess(message, 10000); // 显示10秒
  
  // 如果有错误，显示详细信息
  if (result.errors && result.errors.length > 0) {
    console.error('索引重建错误:', result.errors);
  }
}
```

### 知识图谱加载
```javascript
async function loadKnowledgeGraph() {
  try {
    // 先检查索引状态
    const status = await fetch(`${API}/wiki/status`).then(r => r.json());
    
    if (!status.indexed) {
      document.getElementById('wikiGraph').innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-title">知识图谱未就绪</div>
          <div class="empty-desc">请先建立索引</div>
          <button class="btn btn-primary" onclick="rebuildIndex()">重建索引</button>
        </div>
      `;
      return;
    }
    
    // 加载图谱数据
    const graphData = await fetch(`${API}/wiki/graph`).then(r => r.json());
    wikiState.graphData = graphData;
    
    // 渲染知识图谱
    renderKnowledgeGraph(graphData);
    
  } catch (error) {
    console.error('加载知识图谱失败:', error);
    document.getElementById('wikiGraph').innerHTML = `
      <div class="error-state">
        <div class="error-icon">❌</div>
        <div class="error-title">加载知识图谱失败</div>
        <div class="error-desc">${error.message}</div>
      </div>
    `;
  }
}
```

## 数据渲染

### 搜索结果渲染
```javascript
function renderSearchResults(data) {
  const container = document.getElementById('wikiResults');
  if (!container) return;
  
  if (!data.results || data.results.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-title">未找到相关结果</div>
        <div class="empty-desc">尝试使用其他搜索模式或关键词</div>
      </div>
    `;
    return;
  }
  
  // 构建结果HTML
  const resultsHtml = data.results.map((result, index) => {
    const scorePercent = Math.round((result.score || 0) * 100);
    const sourceFile = result.metadata?.source || '未知来源';
    
    return `
      <div class="wiki-result-item">
        <div class="result-header">
          <div class="result-rank">#${index + 1}</div>
          <div class="result-score">
            <div class="score-bar">
              <div class="score-fill" style="width: ${scorePercent}%"></div>
            </div>
            <span class="score-text">${scorePercent}%</span>
          </div>
        </div>
        <div class="result-content">${highlightText(result.text, data.query)}</div>
        <div class="result-meta">
          <span class="result-source">📄 ${sourceFile}</span>
          ${result.metadata?.page ? `<span class="result-page">📖 第${result.metadata.page}页</span>` : ''}
        </div>
      </div>
    `;
  }).join('');
  
  // 构建统计信息
  const statsHtml = `
    <div class="search-stats">
      <div class="stat-item">
        <span class="stat-label">搜索模式:</span>
        <span class="stat-value">${searchModes[data.mode]?.name || data.mode}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">耗时:</span>
        <span class="stat-value">${(data.time_cost || 0).toFixed(2)}秒</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">结果数:</span>
        <span class="stat-value">${data.results.length}个</span>
      </div>
    </div>
  `;
  
  container.innerHTML = statsHtml + resultsHtml;
}
```

### 文件列表渲染
```javascript
function renderFileList() {
  const container = document.getElementById('wikiFiles');
  if (!container) return;
  
  if (!wikiState.fileList.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📁</div>
        <div class="empty-title">wiki目录为空</div>
        <div class="empty-desc">将Markdown文件放入wiki/目录即可自动索引</div>
      </div>
    `;
    return;
  }
  
  const filesHtml = wikiState.fileList.map(file => {
    const size = formatFileSize(file.size);
    const modified = formatDate(file.modified);
    const ext = file.name.split('.').pop().toLowerCase();
    
    return `
      <div class="wiki-file-item" data-path="${file.path}">
        <div class="file-icon">${getFileIcon(ext)}</div>
        <div class="file-info">
          <div class="file-name">${file.name}</div>
          <div class="file-meta">
            <span class="file-size">${size}</span>
            <span class="file-modified">${modified}</span>
            <span class="file-path">${file.path}</span>
          </div>
        </div>
        <div class="file-actions">
          <button class="btn-icon" onclick="previewFile('${file.path}')" title="预览">👁️</button>
          <button class="btn-icon" onclick="openFile('${file.path}')" title="打开">📂</button>
          <button class="btn-icon" onclick="deleteFile('${file.path}')" title="删除">🗑️</button>
        </div>
      </div>
    `;
  }).join('');
  
  container.innerHTML = filesHtml;
}
```

### 知识图谱渲染
```javascript
function renderKnowledgeGraph(graphData) {
  const container = document.getElementById('wikiGraph');
  if (!container) return;
  
  // 清空容器
  container.innerHTML = '';
  
  // 创建画布
  const canvas = document.createElement('canvas');
  canvas.id = 'graphCanvas';
  canvas.width = container.clientWidth;
  canvas.height = 600;
  container.appendChild(canvas);
  
  // 初始化图谱渲染器
  const graphRenderer = new GraphRenderer(canvas, graphData);
  graphRenderer.render();
  
  // 添加控制面板
  const controls = createGraphControls(graphRenderer);
  container.appendChild(controls);
}
```

## 工具函数

### 文件大小格式化
```javascript
function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
```

### 文本高亮
```javascript
function highlightText(text, query) {
  if (!query || !text) return escapeHtml(text);
  
  const escapedQuery = escapeRegExp(query);
  const regex = new RegExp(`(${escapedQuery})`, 'gi');
  
  return escapeHtml(text).replace(regex, '<mark>$1</mark>');
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
```

### 文件图标映射
```javascript
function getFileIcon(extension) {
  const iconMap = {
    'md': '📝',
    'txt': '📄',
    'pdf': '📕',
    'doc': '📘',
    'docx': '📘',
    'xls': '📊',
    'xlsx': '📊',
    'ppt': '📽️',
    'pptx': '📽️',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'png': '🖼️',
    'gif': '🖼️',
    'zip': '📦',
    'rar': '📦',
    '7z': '📦'
  };
  
  return iconMap[extension] || '📁';
}
```

## 样式设计要点

### 搜索模式指示器
```css
.search-mode-indicator {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  margin-left: 8px;
}

.mode-naive { background-color: #dbeafe; color: #1e40af; }
.mode-local { background-color: #fef3c7; color: #92400e; }
.mode-global { background-color: #e0e7ff; color: #3730a3; }
.mode-hybrid { background-color: #fce7f3; color: #9d174d; }
.mode-mix { background-color: #dcfce7; color: #166534; }
```

### 结果项样式
```css
.wiki-result-item {
  background: white;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  transition: all 0.2s;
}

.wiki-result-item:hover {
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.result-rank {
  font-size: 14px;
  font-weight: 600;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
}

.score-bar {
  width: 100px;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #3b82f6);
  transition: width 0.5s ease-out;
}
```

### 文件项样式
```css
.wiki-file-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #e5e7eb;
  transition: background-color 0.2s;
}

.wiki-file-item:hover {
  background-color: #f9fafb;
}

.file-icon {
  font-size: 24px;
  margin-right: 12px;
  width: 40px;
  text-align: center;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  font-size: 12px;
  color: #6b7280;
}

.file-meta span {
  margin-right: 12px;
}
```

## 性能优化

### 搜索防抖
```javascript
let searchDebounceTimer = null;

function setupSearchDebounce() {
  const searchInput = document.getElementById('wikiSearchInput');
  
  searchInput.addEventListener('input', () => {
    clearTimeout(searchDebounceTimer);
    
    searchDebounceTimer = setTimeout(() => {
      // 输入长度足够时自动搜索
      const query = searchInput.value.trim();
      if (query.length >= 2) {
        wikiSearch();
      }
    }, 500);
  });
}
```

### 结果缓存
```javascript
const searchCache = new Map();

async function cachedSearch(query, mode) {
  const cacheKey = `${query}|${mode}`;
  
  // 检查缓存
  if (searchCache.has(cacheKey)) {
    const cached = searchCache.get(cacheKey);
    
    // 检查缓存是否过期（5分钟）
    if (Date.now() - cached.timestamp < 5 * 60 * 1000) {
      return cached.data;
    }
  }
  
  // 执行新搜索
  const data = await performSearch(query, mode);
  
  // 更新缓存
  searchCache.set(cacheKey, {
    data,
    timestamp: Date.now()
  });
  
  // 限制缓存大小
  if (searchCache.size > 50) {
    const keys = Array.from(searchCache.keys());
    searchCache.delete(keys[0]);
  }
  
  return data;
}
```

### 延迟加载
```javascript
// 知识图谱延迟加载
function setupLazyLoading() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting && wikiState.currentTab === 'graph') {
        loadKnowledgeGraph();
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  
  const graphTab = document.querySelector('[data-tab="graph"]');
  if (graphTab) {
    observer.observe(graphTab);
  }
}
```

## 错误处理

### 搜索超时处理
```javascript
async function wikiSearchWithTimeout(query, mode, timeout = 120000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(`${API}/wiki/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, mode }),
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    return await response.json();
    
  } catch (error) {
    clearTimeout(timeoutId);
    
    if (error.name === 'AbortError') {
      throw new Error(`搜索超时（${timeout/1000}秒），请尝试更简单的搜索模式`);
    }
    
    throw error;
  }
}
```

### 优雅降级
```javascript
// 如果混合搜索失败，自动降级
async function adaptiveSearch(query) {
  const modes = ['hybrid', 'mix', 'global', 'local', 'naive'];
  
  for (const mode of modes) {
    try {
      const result = await wikiSearchWithTimeout(query, mode, 60000);
      return { ...result, mode };
    } catch (error) {
      console.warn(`${mode}模式搜索失败:`, error.message);
      
      // 如果是最后一个模式，抛出错误
      if (mode === modes[modes.length - 1]) {
        throw error;
      }
      
      // 否则继续尝试下一个模式
      continue;
    }
  }
}
```

## 扩展性设计

### 插件系统
```javascript
// 搜索结果渲染插件
window.wikiPlugins = window.wikiPlugins || {
  resultRenderers: [],
  fileActions: [],
  graphVisualizers: []
};

function registerResultRenderer(renderer) {
  window.wikiPlugins.resultRenderers.push(renderer);
}

function registerFileAction(action) {
  window.wikiPlugins.fileActions.push(action);
}
```

### 自定义搜索模式
```javascript
// 添加自定义搜索模式
function registerSearchMode(id, config) {
  searchModes[id] = config;
  
  // 更新UI中的选择器
  const select = document.getElementById('wikiSearchMode');
  if (select) {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = config.name;
    select.appendChild(option);
  }
}
```

## 相关模块
- **Overview模块**: 显示系统状态概览
- **Memory模块**: 个人记忆管理
- **LightRAG引擎**: 后端知识检索核心
- **MCP服务**: wiki_mcp提供外部访问接口

---

*最后更新: 2026-04-29*