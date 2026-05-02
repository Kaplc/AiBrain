/* ==================== 变量声明 ==================== */
var allMemories = [];          // 存储所有记忆列表（从API加载）
var searchResults = [];        // 搜索结果列表（临时保存搜索返回的结果）
var searchTimer = null;        // 定时器引用（用于实现防抖延迟）
var activeQuery = '';          // 当前搜索关键词（标记已搜索的状态）
var searchHistory = [];        // 存储搜索历史（从API加载）
var currentTab = 'search';     // 当前激活的 tab

// 整理状态持久化到 window，切换页面后恢复
window._organizeState = window._organizeState || { groups: [], refined: [], busy: false, appliedGroups: [] };
var organizeGroups = window._organizeState.groups;
var organizeRefined = window._organizeState.refined;
var _organizeBusy = window._organizeState.busy;
var _appliedGroups = window._organizeState.appliedGroups; // 已写入的组索引

function _saveOrganizeState() {
  window._organizeState.groups = organizeGroups;
  window._organizeState.refined = organizeRefined;
  window._organizeState.busy = _organizeBusy;
  window._organizeState.appliedGroups = _appliedGroups;
}

/* ==================== 页面初始化 ==================== */
function onPageLoad() {
  // 搜索框回车
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchMemory();
  });
  // 保存框 Ctrl+Enter
  document.getElementById('storeInput').addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') storeMemory();
  });
  loadAll();
  loadSearchHistory();
  // 恢复整理状态
  restoreOrganizeState();
}

/* ==================== 整理状态恢复 ==================== */
function restoreOrganizeState() {
  // 重新从 window 同步最新状态（老 async 函数可能在页面切走后完成了更新）
  organizeGroups = window._organizeState.groups || [];
  organizeRefined = window._organizeState.refined || [];
  _organizeBusy = window._organizeState.busy || false;
  _appliedGroups = window._organizeState.appliedGroups || [];

  // 如果正在分析中，自动重新触发
  if (_organizeBusy) {
    switchTab('organize');
    _organizeBusy = false;
    _saveOrganizeState();
    startOrganize();
    return;
  }
  if (!organizeGroups.length && !organizeRefined.length) return;
  var contentEl = document.getElementById('organizeContent');
  if (!contentEl) return;

  // 切换到整理 tab
  switchTab('organize');

  // 重建分组卡片
  var html = '<div class="organize-header"><span>恢复整理状态（' + organizeGroups.length + ' 组）</span></div>';
  html += '<div class="organize-groups" id="organizeGroups">';
  organizeGroups.forEach(function(g, gi) {
    var isApplied = _appliedGroups.indexOf(gi) !== -1;
    var hasRefined = organizeRefined.some(function(r) { return r.group_id === gi; });
    var items = g.memories.map(function(m, mi) { return '<div class="og-item"><span class="og-idx">' + (mi+1) + '</span>' + escHtml(m.text) + '</div>'; }).join('');
    var cardClass = isApplied ? 'organize-group-card og-applied' : 'organize-group-card';
    var btnHtml = isApplied ? '<button class="btn-secondary-sm og-refine-btn" disabled>已写入</button>' :
      hasRefined ? '<button class="btn-secondary-sm og-refine-btn" disabled>已精炼</button>' :
      '<button class="btn-secondary-sm og-refine-btn" onclick="refineGroup(' + gi + ')">精炼此组</button>';
    html += '<div class="' + cardClass + '">' +
      '<div class="og-label">组 ' + (gi+1) + ' · 相似度 ' + g.similarity + ' · ' + g.memories.length + ' 条' + btnHtml + '</div>' +
      items + '</div>';
  });
  html += '</div><div id="organizeRefined" class="organize-refined"></div>';
  contentEl.innerHTML = html;

  // 重建已精炼的卡片内结果
  var cards = document.querySelectorAll('.organize-group-card');
  organizeRefined.forEach(function(item, idx) {
    var gi = item.group_id;
    var card = cards[gi];
    if (!card) return;
    // 移除 og-applied 以外的精炼按钮禁用已经处理
    var refineBtn = card.querySelector('.og-refine-btn');
    if (refineBtn) { refineBtn.textContent = '已精炼'; refineBtn.disabled = true; }
    card.classList.remove('og-applied');

    var div = document.createElement('div');
    div.className = 'og-refine-result';
    var refinedClass = item.refined ? 'refined' : '';
    div.innerHTML =
      '<div class="og-refine-divider"></div>' +
      '<div class="og-refine-label ' + refinedClass + '">精炼结果' + (item.refined ? '' : '（降级）') + '</div>' +
      '<div class="organize-refined-text" contenteditable="true" id="refinedText' + idx + '">' + escHtml(item.refined_text) + '</div>' +
      '<div class="organize-category">分类: ' + escHtml(item.category || 'unknown') + '</div>' +
      '<div class="og-refine-actions">' +
      '<div class="organize-check"><input type="checkbox" id="refinedCheck' + idx + '" checked><label for="refinedCheck' + idx + '">确认合并</label></div>' +
      '<button class="btn btn-sm btn-primary" onclick="applySingleRefine(' + idx + ')">确认修改</button></div>';
    card.appendChild(div);
  });

  updateRefineFooter();
}

/* ==================== Tab 切换 ==================== */
function switchTab(tab) {
  currentTab = tab;
  // 更新 tab 按钮样式
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  // 显示/隐藏面板
  document.getElementById('tabSearch').style.display = tab === 'search' ? '' : 'none';
  document.getElementById('tabStore').style.display = tab === 'store' ? '' : 'none';
  document.getElementById('tabOrganize').style.display = tab === 'organize' ? '' : 'none';
  // 切换到保存时显示全部记忆
  if (tab === 'store' && !activeQuery) {
    renderList(allMemories, false, 'allMemoryList');
  }
}

/* ==================== API 请求 ==================== */
async function api(path, data) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  return r.json();
}

/* ==================== 保存记忆 ==================== */
async function storeMemory() {
  const text = document.getElementById('storeInput').value.trim();
  if (!text) return;
  try {
    const r = await api('/store', {text});
    if (r.error) { toast(r.error, 'error'); return; }
    toast(r.result, 'success');
    document.getElementById('storeInput').value = '';
    loadAll();
  } catch(e) { toast('连接失败', 'error'); }
}

/* ==================== 防抖搜索 ==================== */
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchMemory, 500);
}

/* ==================== 搜索记忆 ==================== */
async function searchMemory() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;
  activeQuery = query;
  try {
    const r = await api('/search', {query});
    searchResults = r.results || [];
    loadSearchHistory();
    renderList(searchResults, true, 'memoryList');
  } catch(e) { toast('搜索失败', 'error'); }
}

/* ==================== 加载全部数据 ==================== */
async function loadAll() {
  updateStats();
  try {
    const r = await api('/list', {});
    allMemories = r.memories || [];
    // 搜索 tab：有搜索词则刷新搜索结果，否则保持空状态
    if (activeQuery) {
      renderList(searchResults, true, 'memoryList');
    }
    // 保存 tab 可见时刷新全部记忆列表
    if (currentTab === 'store') {
      renderList(allMemories, false, 'allMemoryList');
    }
  } catch(e) { console.error('[memory] loadAll error:', e); }
}

/* ==================== 更新统计数字 ==================== */
async function updateStats() {
  try {
    const cntRes = await fetchJson(API + '/memory-count');
    const el = document.getElementById('totalCount');
    if (el) animateCount(el, cntRes.count || 0);
  } catch(e) {
    const el = document.getElementById('totalCount');
    if (el) el.textContent = allMemories.length;
  }
}

/* ==================== 数字递增动画 ==================== */
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
async function deleteMemory(id) {
  try {
    const r = await api('/delete', {memory_id: id});
    if (r.error) { toast(r.error, 'error'); return; }
    toast(r.result, 'success');
    allMemories = allMemories.filter(m => m.id !== id);
    searchResults = searchResults.filter(m => m.id !== id);
    updateStats();
    // 刷新当前可见的列表
    if (currentTab === 'search') renderList(activeQuery ? searchResults : allMemories, !!activeQuery, 'memoryList');
    if (currentTab === 'store') renderList(allMemories, false, 'allMemoryList');
  } catch(e) { toast('删除失败', 'error'); }
}

/* ==================== 渲染列表 ==================== */
function renderList(items, isSearch, containerId) {
  var el = document.getElementById(containerId || 'memoryList');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">' + (isSearch ? '🔍' : '🧠') + '</div><div class="empty-text">' + (isSearch ? '没有找到相关记忆' : '还没有任何记忆') + '</div></div>';
    return;
  }
  el.innerHTML = items.map(m =>
    '<div class="memory-card ' + (isSearch ? 'search-result' : '') + '">' +
      '<div class="memory-content">' +
        '<div class="memory-text">' + escHtml(m.text) + '</div>' +
        '<div class="memory-meta">' +
          '<span class="memory-time">' + formatTime(m.timestamp) + '</span>' +
          (m.score !== undefined ? '<span class="memory-score">相似度 ' + (m.score*100).toFixed(1) + '%</span>' : '') +
          '<span class="memory-id">' + (m.id||'').slice(0,8) + '...</span>' +
        '</div>' +
      '</div>' +
      '<button class="del-btn" onclick="deleteMemory(\'' + m.id + '\')" title="删除">✕</button>' +
    '</div>'
  ).join('');
}

/* ==================== 工具函数 ==================== */
function formatTime(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
  catch { return ts.slice(0,16); }
}

/* ==================== 搜索历史 ==================== */
async function loadSearchHistory() {
  try {
    const r = await fetch(API + '/search-history');
    const data = await r.json();
    searchHistory = (data.history || []).map(h => h.query);
    renderSearchHistory();
  } catch(e) { console.error(e); }
}

function renderSearchHistory() {
  const el = document.getElementById('searchHistory');
  if (!el) return;
  if (!searchHistory.length) {
    el.innerHTML = '<div class="sh-empty">暂无搜索历史</div>';
    return;
  }
  el.innerHTML = searchHistory.map(h =>
    '<div class="history-item" onclick="searchFromHistory(\'' + escHtml(h) + '\')">' + escHtml(h) + '</div>'
  ).join('');
}

function searchFromHistory(query) {
  document.getElementById('searchInput').value = query;
  closeSearchHistory();
  searchMemory();
}

function toggleSearchHistory() {
  var dd = document.getElementById('searchHistoryDropdown');
  if (!dd) return;
  var isOpen = dd.style.display !== 'none';
  dd.style.display = isOpen ? 'none' : '';
  if (!isOpen) renderSearchHistory();
}

function closeSearchHistory() {
  var dd = document.getElementById('searchHistoryDropdown');
  if (dd) dd.style.display = 'none';
}

async function clearSearchHistory() {
  try {
    await fetch(API + '/search-history', {method: 'DELETE'});
    searchHistory = [];
    renderSearchHistory();
  } catch(e) { console.error(e); }
}

// 点击外部关闭下拉
document.addEventListener('click', function(e) {
  var wrap = document.querySelector('.search-history-wrap');
  if (wrap && !wrap.contains(e.target)) closeSearchHistory();
});

/* ==================== 记忆整理 ==================== */
async function startOrganize() {
  if (_organizeBusy) return;
  _organizeBusy = true;
  _saveOrganizeState();
  var btn = document.getElementById('organizeBtn');
  if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }
  var contentEl = document.getElementById('organizeContent');
  contentEl.innerHTML = '<div class="organize-loading">正在分析记忆相似度...</div>';

  var threshold = parseFloat(document.getElementById('dedupThreshold').value) || 0.85;
  try {
    var r = await api('/organize/dedup', {similarity_threshold: threshold});
    if (r.error) { contentEl.innerHTML = '<div class="organize-loading">错误: ' + escHtml(r.error) + '</div>'; _organizeBusy = false; _saveOrganizeState(); if (btn) { btn.disabled = false; btn.textContent = '分析'; } return; }
    organizeGroups = r.groups || [];
    _saveOrganizeState();
    var total = r.total_memories || 0;
    var grouped = r.grouped_count || 0;

    if (!organizeGroups.length) {
      contentEl.innerHTML = '<div class="empty"><div class="empty-icon">✅</div><div class="empty-text">没有发现重复的记忆（共 ' + total + ' 条）</div></div>';
      _organizeBusy = false; _saveOrganizeState(); if (btn) { btn.disabled = false; btn.textContent = '分析'; }
      return;
    }

    // 渲染分组
    var html = '<div class="organize-header"><span>共 ' + total + ' 条，发现 ' + organizeGroups.length + ' 组相似（' + grouped + ' 条）</span></div>';
    html += '<div class="organize-groups" id="organizeGroups">';
    html += organizeGroups.map(function(g, gi) {
      var items = g.memories.map(function(m, mi) { return '<div class="og-item"><span class="og-idx">' + (mi+1) + '</span>' + escHtml(m.text) + '</div>'; }).join('');
      return '<div class="organize-group-card">' +
        '<div class="og-label">组 ' + (gi+1) + ' · 相似度 ' + g.similarity + ' · ' + g.memories.length + ' 条' +
        '<button class="btn-secondary-sm og-refine-btn" onclick="refineGroup(' + gi + ')">精炼此组</button></div>' +
        items + '</div>';
    }).join('');
    html += '</div><div id="organizeRefined" class="organize-refined"></div>';
    contentEl.innerHTML = html;
    _organizeBusy = false; _saveOrganizeState(); if (btn) { btn.disabled = false; btn.textContent = '分析'; }
  } catch(e) {
    contentEl.innerHTML = '<div class="organize-loading">请求失败: ' + escHtml(e.message) + '</div>';
    _organizeBusy = false; _saveOrganizeState(); if (btn) { btn.disabled = false; btn.textContent = '分析'; }
  }
}

async function refineGroup(groupIndex) {
  if (!organizeGroups[groupIndex]) return;

  // 检查该组是否已精炼
  var existing = organizeRefined.find(function(r) { return r.group_id === groupIndex; });
  if (existing) { toast('该组已精炼', 'info'); return; }

  // 在对应卡片上显示加载状态
  var card = document.querySelectorAll('.organize-group-card')[groupIndex];
  if (!card) return;
  var btn = card.querySelector('.og-refine-btn');
  if (btn) { btn.disabled = true; btn.textContent = '精炼中...'; }

  try {
    var r = await api('/organize/refine', {groups: [organizeGroups[groupIndex]]});
    if (r.error) { toast('精炼失败: ' + r.error, 'error'); if (btn) { btn.disabled = false; btn.textContent = '精炼此组'; } return; }
    var newRefined = r.refined || [];
    newRefined.forEach(function(item) { item.group_id = groupIndex; });
    organizeRefined = organizeRefined.concat(newRefined);
    _saveOrganizeState();

    // 在卡片内插入精炼结果
    var refineIdx = organizeRefined.length - newRefined.length; // 索引基址
    newRefined.forEach(function(item, ri) {
      var idx = refineIdx + ri;
      var div = document.createElement('div');
      div.className = 'og-refine-result';
      var refinedClass = item.refined ? 'refined' : '';
      div.innerHTML =
        '<div class="og-refine-divider"></div>' +
        '<div class="og-refine-label ' + refinedClass + '">精炼结果' + (item.refined ? '' : '（降级）') + '</div>' +
        '<div class="organize-refined-text" contenteditable="true" id="refinedText' + idx + '">' + escHtml(item.refined_text) + '</div>' +
        '<div class="organize-category">分类: ' + escHtml(item.category || 'unknown') + '</div>' +
        '<div class="og-refine-actions">' +
        '<div class="organize-check"><input type="checkbox" id="refinedCheck' + idx + '" checked><label for="refinedCheck' + idx + '">确认合并</label></div>' +
        '<button class="btn btn-sm btn-primary" onclick="applySingleRefine(' + idx + ')">确认修改</button></div>';
      card.appendChild(div);
    });

    if (btn) { btn.textContent = '已精炼'; btn.disabled = true; }
    updateRefineFooter();
  } catch(e) {
    toast('精炼失败: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = '精炼此组'; }
  }
}

async function applySingleRefine(refineIndex) {
  var item = organizeRefined[refineIndex];
  if (!item) return;
  var textEl = document.getElementById('refinedText' + refineIndex);
  var newText = textEl ? textEl.innerText.trim() : item.refined_text;
  if (!newText) { toast('精炼内容为空', 'error'); return; }

  try {
    var r = await api('/organize/apply', {items: [{delete_ids: item.original_ids, new_text: newText, category: item.category || 'reference'}]});
    if (r.error) { toast('写入失败: ' + r.error, 'error'); return; }
    toast('已合并该组记忆（删除 ' + item.original_ids.length + ' 条，新增 1 条）');

    // 从数据中移除已写入的项
    var gid = item.group_id;
    organizeRefined = organizeRefined.filter(function(_, i) { return i !== refineIndex; });
    if (_appliedGroups.indexOf(gid) === -1) _appliedGroups.push(gid);
    _saveOrganizeState();

    // 移除该卡片中的精炼结果区域
    var card = document.querySelectorAll('.organize-group-card')[gid];
    if (card) {
      var resultEl = card.querySelector('.og-refine-result');
      if (resultEl) resultEl.remove();
      // 整个卡片标记为已完成
      card.classList.add('og-applied');
      var refineBtn = card.querySelector('.og-refine-btn');
      if (refineBtn) { refineBtn.textContent = '已写入'; refineBtn.disabled = true; }
    }

    updateRefineFooter();

    // 全部写完则重置
    if (!organizeRefined.length && organizeGroups.length) {
      var allApplied = document.querySelectorAll('.organize-group-card.og-applied').length === organizeGroups.length;
      if (allApplied) {
        organizeGroups = [];
        organizeRefined = [];
        _appliedGroups = [];
        _saveOrganizeState();
        document.getElementById('organizeContent').innerHTML = '<div class="empty"><div class="empty-icon">✅</div><div class="empty-text">整理完成</div></div>';
        loadAll();
      }
    }
  } catch(e) { toast('写入失败: ' + e.message, 'error'); }
}

function refineAllGroups() {
  if (!organizeGroups.length) return;
  var unrefinedIndices = [];
  for (var i = 0; i < organizeGroups.length; i++) {
    if (!organizeRefined.find(function(r) { return r.group_id === i; })) {
      unrefinedIndices.push(i);
    }
  }
  if (!unrefinedIndices.length) { toast('所有组已精炼', 'info'); return; }
  unrefinedIndices.forEach(function(idx) { refineGroup(idx); });
}

// 更新底部操作栏
function updateRefineFooter() {
  var footer = document.getElementById('organizeRefined');
  if (!footer) return;
  if (!organizeRefined.length) { footer.innerHTML = ''; return; }
  var unrefinedCount = 0;
  for (var i = 0; i < organizeGroups.length; i++) {
    if (!organizeRefined.find(function(r) { return r.group_id === i; })) unrefinedCount++;
  }
  var html = '<div class="organize-footer-bar">' +
    '<span class="organize-footer-stat">已精炼 ' + organizeRefined.length + '/' + organizeGroups.length + ' 组</span>' +
    '<div class="organize-actions">' +
    (unrefinedCount > 0 ? '<button class="btn-secondary-sm" onclick="refineAllGroups()">精炼剩余 ' + unrefinedCount + ' 组</button>' : '') +
    '<button class="btn btn-sm btn-primary" onclick="applyOrganize()">确认写入</button></div></div>';
  footer.innerHTML = html;
}

async function applyOrganize() {
  if (!organizeRefined.length) return;
  var items = [];
  for (var i = 0; i < organizeRefined.length; i++) {
    var check = document.getElementById('refinedCheck' + i);
    if (!check || !check.checked) continue;
    var textEl = document.getElementById('refinedText' + i);
    var newText = textEl ? textEl.innerText.trim() : organizeRefined[i].refined_text;
    if (!newText) continue;
    items.push({delete_ids: organizeRefined[i].original_ids, new_text: newText, category: organizeRefined[i].category || 'reference'});
  }
  if (!items.length) { toast('没有勾选任何项', 'error'); return; }
  try {
    var r = await api('/organize/apply', {items: items});
    if (r.error) { toast('写入失败: ' + r.error, 'error'); return; }
    toast('已合并 ' + r.applied + ' 组记忆（删除 ' + r.deleted + ' 条，新增 ' + r.added + ' 条）');
    organizeGroups = [];
    organizeRefined = [];
    _saveOrganizeState();
    document.getElementById('organizeContent').innerHTML = '<div class="empty"><div class="empty-icon">✅</div><div class="empty-text">整理完成</div></div>';
    loadAll();
  } catch(e) { toast('写入失败: ' + e.message, 'error'); }
}
