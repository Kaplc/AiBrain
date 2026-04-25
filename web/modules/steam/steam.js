/* 记忆流页面 - 两栏布局 */
var _streamTimer = null;

function onPageLoad() {
  loadStream();
  // 每 2 秒轮询新记录
  if (_streamTimer) clearInterval(_streamTimer);
  _streamTimer = setInterval(loadStream, 2000);
}

function cleanup() {
  if (_streamTimer) { clearInterval(_streamTimer); _streamTimer = null; }
}

async function loadStream() {
  try {
    // 获取 MCP 调用和搜索记录
    const [storeRes, searchRes] = await Promise.all([
      fetchJson(API + '/stream?action=store&limit=30'),
      fetchJson(API + '/stream?action=search&limit=30'),
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
  } catch(e) { console.error('[stream] load failed:', e); }
}

function renderList(listId, items, showDelete) {
  const listEl = document.getElementById(listId);
  if (!listEl) return;

  if (!items.length) {
    const emptyText = listId === 'storeList' ? '暂无写入记录' : '暂无查询记录';
    listEl.innerHTML = `<div class="steam-empty">${emptyText}</div>`;
    return;
  }

  let html = '';
  items.forEach(item => {
    const actionLabel = item.action === 'store' ? '存入' : item.action === 'search' ? '搜索' : '删除';
    const dotClass = 'steam-dot ' + item.action;
    const timeStr = (item.created_at || '').slice(11, 19);
    const text = item.content || item.memory_id || '';

    html += `<div class="steam-item" data-id="${item.id}">
      <div class="${dotClass}"></div>
      <div class="steam-body">
        <span style="font-weight:600;color:#a78bfa;margin-right:6px">${actionLabel}</span>
        <span class="steam-text">${escapeHtml(text)}</span>
      </div>
      <div class="steam-time">${timeStr}</div>
    </div>`;
  });

  listEl.innerHTML = html;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}