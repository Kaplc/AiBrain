/* ==================== 变量声明 ==================== */
var allMemories = [];          // 存储所有记忆列表（从API加载）
var searchResults = [];        // 搜索结果列表（临时保存搜索返回的结果）
var searchTimer = null;        // 定时器引用（用于实现防抖延迟）
var activeQuery = '';          // 当前搜索关键词（标记已搜索的状态）

/* ==================== 搜索历史 ==================== */
var searchHistory = [];  // 存储搜索历史（从API加载，代替localStorage）

/* ==================== 页面初始化 ==================== */
function onPageLoad() {
  console.log('[memory] onPageLoad start');
  // 监听键盘事件：检查是否同时按下了Ctrl和Enter键，是则调用storeMemory()
  // 流程：keydown事件 → 检测e.ctrlKey && e.key==='Enter' → storeMemory()
  document.getElementById('storeInput').addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') storeMemory();
  });

  // 监听键盘事件：检测是否按下Enter键，是则调用searchMemory()
  // 流程：keydown事件 → 检测e.key==='Enter' → searchMemory()
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchMemory();
  });

  // 加载统计数据：调用loadAll()获取记忆总数并更新页面显示
  console.log('[memory] calling loadAll and loadSearchHistory');
  loadAll();

  // 加载搜索历史：从API获取历史记录并渲染到侧边栏
  loadSearchHistory();
  console.log('[memory] onPageLoad done');
}

/* ==================== API 请求 ==================== */
// 封装fetch POST请求，发送JSON数据，返回解析后的JSON响应
// 参数：path接口路径，data要发送的数据对象
// 返回：Promise<response.json()>
async function api(path, data) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  return r.json();
}

/* ==================== 保存记忆 ==================== */
// 获取textarea内容，调用/store接口保存记忆
// 流程：获取输入 → 非空校验 → api('/store') → 成功则清空输入框+更新统计
// 错误处理：显示toast提示错误信息
async function storeMemory() {
  const text = document.getElementById('storeInput').value.trim();
  if (!text) return;
  try {
    const r = await api('/store', {text});
    if (r.error) { toast(r.error, 'error'); return; }
    toast('✅ ' + r.result, 'success');
    document.getElementById('storeInput').value = '';
    loadAll();  // 保存成功后更新统计数字
  } catch(e) { toast('连接失败', 'error'); }
}

/* ==================== 防抖搜索 ==================== */
// 清除之前的定时器，设置新的500ms延迟后执行searchMemory()
// 作用：避免用户快速输入时每字都触发搜索，减少服务器压力
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchMemory, 500);
}

/* ==================== 搜索记忆 ==================== */
// 从输入框获取关键词，调用/search接口获取相似记忆
// 流程：获取输入 → 设为activeQuery → api('/search') → 保存结果 → 添加历史 → 更新标题 → 渲染列表
// 搜索结果通过renderList(items, true)显示在右侧区域
async function searchMemory() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;
  activeQuery = query;
  console.log('[memory] searchMemory start', query);
  try {
    const r = await api('/search', {query});
    searchResults = r.results || [];
    console.log('[memory] search results:', searchResults.length);
    loadSearchHistory();                    // 刷新搜索历史（后端在/search时已保存）
    updateListTitle(`搜索结果: ${query}`);        // 显示当前搜索关键词
    renderList(searchResults, true);              // isSearch=true表示搜索结果样式
  } catch(e) { toast('搜索失败', 'error'); }
}

/* ==================== 加载统计数据 ==================== */
// 调用/memory-count获取数字，同时加载记忆列表并显示
// 统计数字异步递增动画，无需等模型
async function loadAll() {
  console.log('[memory] loadAll start');
  updateStats();  // 先显示已知数字

  // 异步加载记忆列表（渲染到右侧区域）
  try {
    const r = await api('/list', {});
    allMemories = r.memories || [];
    console.log('[memory] list loaded:', allMemories.length, 'memories');
    if (!activeQuery) {
      renderList(allMemories, false);  // 无搜索关键词时显示全部记忆
      updateListTitle('记忆列表');
    }
  } catch(e) { console.error('[memory] loadAll error:', e); }
}

/* ==================== 更新统计数字 ==================== */
// 调用/memory-count接口获取记忆总数，更新侧边栏统计显示
// 接口失败时使用本地allMemories.length作为兜底方案
async function updateStats() {
  console.log('[memory] updateStats start');
  try {
    const cntRes = await fetchJson(API + '/memory-count');
    const el = document.getElementById('totalCount');
    if (el) animateCount(el, cntRes.count || 0);
    console.log('[memory] total count:', cntRes.count);
  } catch(e) {
    const el = document.getElementById('totalCount');
    if (el) el.textContent = allMemories.length;
  }
}

/* ==================== 数字递增动画 ==================== */
// 将数字从当前值递增到目标值（每秒步进，视觉上更流畅）
// 参数：el元素，target目标数字
function animateCount(el, target) {
  const current = parseInt(el.textContent) || 0;
  if (current === target) return;
  const diff = target - current;
  const step = Math.max(1, Math.ceil(Math.abs(diff) / 10));
  const interval = setInterval(() => {
    const now = parseInt(el.textContent) || 0;
    const delta = target > now ? Math.min(step, target - now) : Math.max(-step, target - now);
    if (now === target || (delta > 0 ? now >= target : now <= target)) {
      el.textContent = target;
      clearInterval(interval);
    } else {
      el.textContent = now + delta;
    }
  }, 50);
}

/* ==================== 删除记忆 ==================== */
// 调用/delete接口删除指定记忆，删除后更新allMemories和searchResults
// 流程：api('/delete') → 从两个数组中过滤掉该id → 更新统计 → 重新渲染列表
async function deleteMemory(id) {
  try {
    const r = await api('/delete', {memory_id: id});
    if (r.error) { toast(r.error, 'error'); return; }
    toast('🗑️ ' + r.result, 'success');
    allMemories = allMemories.filter(m => m.id !== id);      // 从全部记忆中移除
    searchResults = searchResults.filter(m => m.id !== id); // 从搜索结果中移除
    updateStats();
    renderList(allMemories, false);
  } catch(e) { toast('删除失败', 'error'); }
}

/* ==================== 渲染列表 ==================== */
// 将记忆数组渲染为HTML卡片列表，显示在右侧区域
// 参数：items记忆数组，isSearch是否为搜索结果（影响样式和空状态图标）
// 流程：遍历items → 生成HTML字符串 → 设置innerHTML
// 空状态：数组为空时显示空状态图标和提示文字
function renderList(items, isSearch) {
  const el = document.getElementById('memoryList');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = `<div class="empty">
      <div class="empty-icon">${isSearch ? '🔍' : '🧠'}</div>
      <div class="empty-text">${isSearch ? '没有找到相关记忆' : '还没有任何记忆'}</div>
    </div>`;
    return;
  }
  el.innerHTML = items.map(m => `
    <div class="memory-card ${isSearch ? 'search-result' : ''}">
      <div class="memory-content">
        <div class="memory-text">${escHtml(m.text)}</div>
        <div class="memory-meta">
          <span class="memory-time">🕐 ${formatTime(m.timestamp)}</span>
          ${m.score !== undefined ? `<span class="memory-score">相似度 ${(m.score*100).toFixed(1)}%</span>` : ''}
          ${m.hit_count !== undefined ? `<span class="memory-hits">${m.hit_count}</span>` : ''}
          ${m.decay_score !== undefined ? `<span class="memory-decay">${m.decay_score.toFixed(2)}</span>` : ''}
          <span class="memory-id">${(m.id||'').slice(0,8)}...</span>
        </div>
      </div>
      <button class="del-btn" onclick="deleteMemory('${m.id}')" title="删除">✕</button>
    </div>
  `).join('');
}

/* ==================== 更新列表标题 ==================== */
// 修改右侧列表区域的标题文字，用于显示当前搜索关键词
function updateListTitle(title) {
  const el = document.getElementById('listTitle');
  if (el) el.textContent = title;
}

/* ==================== 工具函数 ==================== */
// 时间格式化：将时间戳转换为"MM-DD HH:mm"格式
// 使用toLocaleString并指定中文 locale 确保格式一致
function formatTime(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
  catch { return ts.slice(0,16); }
}

/* ==================== 加载搜索历史 ==================== */
// 从API获取搜索历史记录，渲染到侧边栏
async function loadSearchHistory() {
  console.log('[memory] loadSearchHistory start');
  try {
    const r = await fetch(API + '/search-history');
    const data = await r.json();
    searchHistory = (data.history || []).map(h => h.query);
    console.log('[memory] search history:', searchHistory.length, 'items');
    renderSearchHistory();
  } catch(e) { console.error('[memory] loadSearchHistory error:', e); }
}

/* ==================== 搜索历史 ==================== */
// 添加搜索历史：调用API保存到数据库，然后更新本地数组并重新渲染
// 后端会自动去重并保持最多20条
async function addSearchHistory(query) {
  try {
    await api('/search-history', {query});
    searchHistory = searchHistory.filter(h => h !== query);  // 移除已存在的相同记录
    searchHistory.unshift(query);                               // 添加到数组开头
    searchHistory = searchHistory.slice(0, 20);                // 限制最多20条
    renderSearchHistory();
  } catch(e) { console.error(e); }
}

// 渲染搜索历史：将本地searchHistory数组生成HTML显示在侧边栏
// 每个历史项绑定onclick事件，点击时调用searchFromHistory重新搜索
function renderSearchHistory() {
  const el = document.getElementById('searchHistory');
  if (!el) return;
  if (!searchHistory.length) {
    el.innerHTML = '<div style="font-size:12px;color:#64748b">暂无搜索历史</div>';
    return;
  }
  el.innerHTML = searchHistory.map(h => `<div class="history-item" onclick="searchFromHistory('${escHtml(h)}')">🔍 ${escHtml(h)}</div>`).join('');
}

// 从历史记录搜索：将历史项的关键词填入搜索框并触发搜索
// 流程：设置输入框value → 调用searchMemory()
function searchFromHistory(query) {
  document.getElementById('searchInput').value = query;
  searchMemory();
}