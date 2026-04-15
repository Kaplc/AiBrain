/* 记忆页面 */
var allMemories = [];
var searchResults = [];
var currentTab = 'all';
var searchTimer = null;

function onPageLoad() {
  document.getElementById('storeInput').addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') storeMemory();
  });
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchMemory();
  });
  loadAll();
}

async function api(path, data) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  return r.json();
}

async function storeMemory() {
  const text = document.getElementById('storeInput').value.trim();
  if (!text) return;
  try {
    const r = await api('/store', {text});
    if (r.error) { toast(r.error, 'error'); return; }
    toast('✅ ' + r.result, 'success');
    document.getElementById('storeInput').value = '';
    loadAll();
  } catch(e) { toast('连接失败', 'error'); }
}

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchMemory, 500);
}

async function searchMemory() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) { switchTab('all'); return; }
  try {
    const r = await api('/search', {query});
    searchResults = r.results || [];
    switchTab('search');
  } catch(e) { toast('搜索失败', 'error'); }
}

async function loadAll() {
  try {
    const r = await api('/list', {});
    allMemories = r.memories || [];
    updateStats();
    if (currentTab === 'all') renderList(allMemories, false);
  } catch(e) { console.error(e); }
}

function updateStats() {
  document.getElementById('totalCount').textContent = allMemories.length;
  const today = new Date().toISOString().slice(0, 10);
  const cnt = allMemories.filter(m => (m.timestamp || '').startsWith(today)).length;
  document.getElementById('todayCount').textContent = cnt;
}

async function deleteMemory(id) {
  try {
    const r = await api('/delete', {memory_id: id});
    if (r.error) { toast(r.error, 'error'); return; }
    toast('🗑️ ' + r.result, 'success');
    allMemories = allMemories.filter(m => m.id !== id);
    searchResults = searchResults.filter(m => m.id !== id);
    updateStats();
    renderList(currentTab === 'all' ? allMemories : searchResults, currentTab === 'search');
  } catch(e) { toast('删除失败', 'error'); }
}

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
          <span class="memory-id">${(m.id||'').slice(0,8)}...</span>
        </div>
      </div>
      <button class="del-btn" onclick="deleteMemory('${m.id}')" title="删除">✕</button>
    </div>
  `).join('');
}

function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tabAll').className = 'tab' + (tab==='all'?' active':'');
  document.getElementById('tabSearch').className = 'tab' + (tab==='search'?' active':'');
  renderList(tab === 'all' ? allMemories : searchResults, tab === 'search');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function formatTime(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
  catch { return ts.slice(0,16); }
}
