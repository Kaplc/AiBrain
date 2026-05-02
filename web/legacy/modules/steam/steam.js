/* 记忆流页面 - 两栏布局 */
var _streamTimer = null;      // 主轮询：fetch 列表（2秒）
var _statusTimer = null;      // 状态轮询：只更新 pending 记录状态（1秒）

function onPageLoad() {
  loadStream();
  // 主轮询：每 2 秒 fetch 列表（新增/删除）
  if (_streamTimer) clearInterval(_streamTimer);
  _streamTimer = setInterval(loadStream, 2000);
  // 状态轮询：每 1 秒检查 pending 记录状态
  startStatusPoll();
}

function cleanup() {
  if (_streamTimer) { clearInterval(_streamTimer); _streamTimer = null; }
  if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null; }
}

// 状态轮询：只更新有 pending 状态记录的状态图标
function startStatusPoll() {
  if (_statusTimer) clearInterval(_statusTimer);
  _statusTimer = setInterval(async () => {
    // 找所有包含 spinner 的 item（pending 状态）
    const pendingEls = [];
    document.querySelectorAll('.steam-spinner').forEach(spin => {
      const item = spin.closest('.steam-item');
      if (item) pendingEls.push(item);
    });
    if (!pendingEls.length) return; // 没有 pending 就跳过
    try {
      const [storeRes, searchRes] = await Promise.all([
        fetchJson(API + '/stream?action=store&days=3'),
        fetchJson(API + '/stream?action=search&days=3'),
      ]);
      const allItems = (storeRes.items || []).concat(searchRes.items || []);
      const statusMap = {};
      allItems.forEach(i => { statusMap[i.id] = i.status; });

      pendingEls.forEach(el => {
        const id = parseInt(el.dataset.id, 10);
        const newStatus = statusMap[id];
        if (!newStatus || newStatus === 'pending') return;
        // 状态变了：更新图标
        let statusHtml = '';
        if (newStatus === 'done') {
          statusHtml = '<div class="steam-status-icon"><span class="steam-check">✓</span></div>';
        } else if (newStatus === 'error') {
          statusHtml = '<div class="steam-status-icon"><span class="steam-error">✗</span></div>';
        }
        const body = el.querySelector('.steam-body');
        if (body) {
          const oldIcon = body.querySelector('.steam-status-icon');
          if (oldIcon) oldIcon.outerHTML = statusHtml;
        }
      });
    } catch {}
  }, 1000);
}

async function loadStream() {
  try {
    // 获取 MCP 调用和搜索记录
    const [storeRes, searchRes] = await Promise.all([
      fetchJson(API + '/stream?action=store&days=3'),
      fetchJson(API + '/stream?action=search&days=3'),
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

  // 先移除 empty 提示和已不在列表中的旧元素
  listEl.querySelectorAll('.steam-empty').forEach(el => el.remove());
  const existingIds = new Set(items.map(i => String(i.id)));
  listEl.querySelectorAll('.steam-item').forEach(el => {
    if (!existingIds.has(el.dataset.id)) el.remove();
  });

  // 逐个处理：更新已有 / 插入新增
  items.forEach((item, index) => {
    const id = String(item.id);
    let el = listEl.querySelector(`.steam-item[data-id="${id}"]`);

    const actionLabel = item.action === 'store' ? '存入' : item.action === 'search' ? '搜索' : '删除';
    const dotClass = 'steam-dot ' + item.action;
    const timeStr = (item.created_at || '').slice(11, 19);
    const text = item.content || item.memory_id || '';

    // 状态图标 HTML
    const status = item.status || '';
    let statusHtml = '';
    if (status === 'pending') {
      statusHtml = '<div class="steam-status-icon"><div class="steam-spinner"></div></div>';
    } else if (status === 'done') {
      statusHtml = '<div class="steam-status-icon"><span class="steam-check">✓</span></div>';
    } else if (status === 'error') {
      statusHtml = '<div class="steam-status-icon"><span class="steam-error">✗</span></div>';
    }

    if (el) {
      // --- 已有元素：只更新变化的部分 ---
      // 状态图标（幂等：比较 outerHTML 避免不必要的 DOM 写）
      const statusEl = el.querySelector('.steam-status-icon');
      const currentStatusHtml = statusEl ? statusEl.outerHTML : '';
      if (currentStatusHtml !== statusHtml) {
        const body = el.querySelector('.steam-body');
        if (body) {
          const oldIcon = body.querySelector('.steam-status-icon');
          if (oldIcon) oldIcon.outerHTML = statusHtml;
          else if (statusHtml) body.insertAdjacentHTML('beforeend', statusHtml);
        }
      }
      // 文本内容（只读场景通常不变，如需可加上）
      const textEl = el.querySelector('.steam-text');
      if (textEl && textEl.textContent !== text) textEl.textContent = text;
    } else {
      // --- 新增元素：创建完整 HTML 插入 ---
      el = document.createElement('div');
      el.className = 'steam-item';
      el.dataset.id = id;
      el.innerHTML = `
        <div class="${dotClass}"></div>
        <div class="steam-body">
          <span style="font-weight:600;color:#a78bfa;margin-right:6px;flex-shrink:0">${actionLabel}</span>
          <span class="steam-text">${escapeHtml(text)}</span>
          ${statusHtml}
        </div>
        <div class="steam-time">${timeStr}</div>`;
      // 按 index 插入到正确位置（保持列表顺序）
      const children = listEl.querySelectorAll('.steam-item');
      if (index < children.length) {
        listEl.insertBefore(el, children[index]);
      } else {
        listEl.appendChild(el);
      }
    }
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}