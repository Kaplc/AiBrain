/* Wiki 页面逻辑 */

var _wikiFiles = [];
var _sortKey = 'modified';
var _sortAsc = false;
var _wikiConfig = null;
var _indexPollTimer = null;  // 索引进度轮询定时器
var _lastIndexDone = -1;     // 上次已完成的文件数，用于判断是否需要刷新列表

/* WikiFile 类在 wiki_file.js 中定义 */

/* ==================== 工具函数 ==================== */

function escAttr(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function formatDate(ts) {
  if (!ts) return '-';
  var d = new Date(ts * 1000);
  var pad = function(n) { return String(n).padStart(2, '0'); };
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

/* ==================== 页面初始化 ==================== */

function onPageLoad() {
  loadWikiConfig().then(function() {
    loadWikiData();
    restoreIndexProgress();
  });
}

function cleanup() {
  if (_indexPollTimer !== null) {
    clearInterval(_indexPollTimer);
    _indexPollTimer = null;
  }
}

// 恢复索引进度 UI 状态（页面加载或切换回来时调用）
async function restoreIndexProgress() {
  try {
    var pdata = await fetchJson(API + '/wiki/index-progress');
    if (pdata.status === 'running') {
      var btn = document.getElementById('btnReindex');
      var progWrap = document.getElementById('indexProgressWrap');
      var progLabel = document.getElementById('indexProgressLabel');
      var progFill = document.getElementById('indexProgressFill');
      var progPct = document.getElementById('indexProgressPct');
      if (btn) { btn.disabled = true; btn.textContent = '索引中...'; }
      if (progWrap) progWrap.style.display = 'block';
      var pct = pdata.total > 0 ? Math.round((pdata.done / pdata.total) * 100) : 0;
      if (progFill) progFill.style.width = pct + '%';
      if (progPct) progPct.textContent = pct + '%';
      if (progLabel) progLabel.textContent = (pdata.current_file || '进行中...') + ' (' + pdata.done + '/' + pdata.total + ')';
      _lastIndexDone = pdata.done;
    } else {
      // 非 running 状态（done/error/idle）：刷新文件列表，确保 index_status 最新
      await loadWikiData();
    }
    // 始终启动轮询，被动检测后端索引状态
    startIndexPoll();
  } catch (e) {
    console.error('[wiki] restoreIndexProgress error:', e);
    startIndexPoll();
  }
}

// 启动索引进度轮询（始终运行，被动检测后端索引状态）
function startIndexPoll() {
  if (_indexPollTimer !== null) return;
  var progLabel = document.getElementById('indexProgressLabel');
  var progFill = document.getElementById('indexProgressFill');
  var progPct = document.getElementById('indexProgressPct');
  var progWrap = document.getElementById('indexProgressWrap');
  var indexLogWrap = document.getElementById('indexLogWrap');
  var btn = document.getElementById('btnReindex');
  var resultDiv = document.getElementById('indexResult');

  _indexPollTimer = setInterval(async function() {
    try {
      var pdata = await fetchJson(API + '/wiki/index-progress');

      if (pdata.status === 'running') {
        // 后端正在索引 → 显示进度 UI
        if (btn) { btn.disabled = true; btn.textContent = '索引中...'; }
        if (progWrap) progWrap.style.display = 'block';
        var pct = pdata.total > 0 ? Math.round((pdata.done / pdata.total) * 100) : 0;
        if (progFill) progFill.style.width = pct + '%';
        if (progPct) progPct.textContent = pct + '%';
        var label = pdata.current_file
          ? '索引: ' + pdata.current_file + ' (' + pdata.done + '/' + pdata.total + ')'
          : ('进行中 ' + pct + '%');
        if (progLabel) progLabel.textContent = label;
        // 刷新日志
        await refreshIndexLog(indexLogWrap);
        if (pdata.done !== _lastIndexDone) {
          _lastIndexDone = pdata.done;
          await loadWikiData();
        }
      } else {
        // 后端非索引状态 → 隐藏进度 UI（仅在之前是 running 时才刷新）
        if (_lastIndexDone !== -1) {
          _lastIndexDone = -1;
          // 先显示100%再隐藏（最后一个文件完成时done=total）
          if (pdata.total > 0) {
            var finalPct = Math.round((pdata.done / pdata.total) * 100);
            if (progFill) progFill.style.width = '100%';
            if (progPct) progPct.textContent = '100%';
          }
          if (progWrap) progWrap.style.display = 'none';
          if (btn) { btn.disabled = false; btn.textContent = '重建索引'; }
          if (indexLogWrap) indexLogWrap.innerHTML = '';
          await loadWikiData();
          if (pdata.status === 'done') {
            if (resultDiv) resultDiv.innerHTML = '<div class="index-result ok">索引完成</div>';
          } else if (pdata.status === 'error') {
            if (resultDiv) resultDiv.innerHTML = '<div class="index-result err">索引出错</div>';
          }
        }
      }
    } catch (e) {
      console.error('[wiki] index poll error:', e);
    }
  }, 500);
}

async function refreshIndexLog(container) {
  try {
    var data = await fetchJson(API + '/wiki/index-log?lines=20');
    if (!container || !data.lines) return;
    var html = data.lines.map(function(line) {
      return '<div class="log-line">' + escHtml(line) + '</div>';
    }).join('');
    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
  } catch (e) {
    // 日志获取失败不阻塞
  }
}

async function loadWikiConfig() {
  try {
    _wikiConfig = await fetchJson(API + '/wiki/settings');
  } catch (e) {
    console.error('[wiki] loadWikiConfig error:', e);
    _wikiConfig = {};
  }
}

/* ==================== 数据加载 ==================== */

async function loadWikiData() {
  var wrap = document.getElementById('wikiTableWrap');
  if (wrap) wrap.innerHTML = '<div class="mini-loading"></div>';
  var indexResult = document.getElementById('indexResult');
  if (indexResult) indexResult.innerHTML = '';

  try {
    var data = await fetchJson(API + '/wiki/list');
    _wikiFiles = _createWikiFiles(Array.isArray(data.files) ? data.files : []);

    // 更新统计面板
    var el;
    el = document.getElementById('wikiFileCount');
    if (el) el.textContent = _wikiFiles.length;
    var totalBytes = 0;
    _wikiFiles.forEach(function(f) { totalBytes += f.sizeBytes || 0; });
    el = document.getElementById('wikiTotalSize');
    if (el) el.textContent = formatSize(totalBytes);
    el = document.getElementById('wikiSizeSub');
    if (el) el.textContent = _wikiFiles.length + ' 个 .md 文件';

    // 索引状态
    var statusEl = document.getElementById('wikiStatus');
    if (statusEl) {
      if (data.indexed) {
        var outOfSync = _wikiFiles.filter(function(f) { return f.indexStatus !== 'synced'; }).length;
        if (outOfSync > 0) {
          statusEl.textContent = '需重建 ' + outOfSync + ' 个文件';
          statusEl.style.color = '#f97316';
        } else {
          statusEl.textContent = '已同步';
          statusEl.style.color = '#86efac';
        }
      } else {
        statusEl.textContent = '未索引';
        statusEl.style.color = '#fde047';
      }
    }

    if (_wikiFiles.length === 0) {
      wrap.innerHTML = '<div class="empty-state">Wiki 目录为空</div>';
      return;
    }

    renderTable(_wikiFiles);
    document.getElementById('wikiFileListMeta').textContent = _wikiFiles.length + ' 个文件';
  } catch (e) {
    console.error('[wiki] loadWikiData error:', e);
    var w2 = document.getElementById('wikiTableWrap');
    if (w2) w2.innerHTML = '<div class="empty-state">加载失败，请检查后端连接</div>';
    var statusEl = document.getElementById('wikiStatus');
    if (statusEl) { statusEl.textContent = '异常'; statusEl.style.color = '#fca5a5'; }
  }
}

/* ==================== 文件列表渲染 ==================== */

function sortFiles(key) {
  if (_sortKey === key) { _sortAsc = !_sortAsc; } else { _sortKey = key; _sortAsc = true; }
  var keyMap = { filename: 'filename', size_bytes: 'sizeBytes', modified: 'modified' };
  var prop = keyMap[key] || key;
  _wikiFiles.sort(function(a, b) {
    var va = a[prop], vb = b[prop];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return _sortAsc ? -1 : 1;
    if (va > vb) return _sortAsc ? 1 : -1;
    return 0;
  });
  renderTable(_wikiFiles);
}

function renderTable(files) {
  var wrap = document.getElementById('wikiTableWrap');
  if (!wrap || !files.length) return;

  var arrow = function(key) {
    if (_sortKey !== key) return '';
    return _sortAsc ? ' \u25B2' : ' \u25BC';
  };

  var html = '<table class="file-table"><thead><tr>'
           + '<th style="width:40px"></th>'
           + '<th onclick="sortFiles(\'filename\')">文件名' + arrow('filename') + '</th>'
           + '<th onclick="sortFiles(\'size_bytes\')">大小' + arrow('size_bytes') + '</th>'
           + '<th onclick="sortFiles(\'modified\')">修改时间' + arrow('modified') + '</th>'
           + '<th>预览</th></tr></thead><tbody>';

  files.forEach(function(f) {
    html += f.toRowHtml();
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function copyPath(path, row) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(path).then(function() { showCopyToast(); });
  } else {
    var ta = document.createElement('textarea');
    ta.value = path;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showCopyToast();
  }
}

function showCopyToast() {
  var existing = document.querySelector('.copy-toast');
  if (existing) existing.remove();
  var toast = document.createElement('div');
  toast.className = 'copy-toast';
  toast.textContent = '路径已复制';
  document.body.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 1200);
}

/* ==================== 索引操作 ==================== */

async function rebuildIndex() {
  var btn = document.getElementById('btnReindex');
  var resultDiv = document.getElementById('indexResult');
  var progWrap = document.getElementById('indexProgressWrap');
  var progFill = document.getElementById('indexProgressFill');

  if (btn) { btn.disabled = true; btn.textContent = '索引中...'; }
  if (resultDiv) resultDiv.innerHTML = '';
  if (progWrap) { progWrap.style.display = 'block'; }
  if (progFill) progFill.style.width = '0%';
  _lastIndexDone = 0;

  try {
    var resp = await fetch(API + '/wiki/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!resp.ok) {
      var errText = await resp.text();
      throw new Error('HTTP ' + resp.status + ': ' + errText);
    }
    var data = await resp.json();

    if (data.error) {
      if (progWrap) progWrap.style.display = 'none';
      if (resultDiv) resultDiv.innerHTML = '<div class="index-result err">索引失败: ' + escHtml(data.error) + '</div>';
      if (btn) { btn.disabled = false; btn.textContent = '重建索引'; }
      return;
    }

    // 启动轮询（共享 startIndexPoll，复用定时器）
    startIndexPoll();

  } catch (e) {
    console.error('[wiki] rebuildIndex error:', e);
    if (progWrap) progWrap.style.display = 'none';
    if (resultDiv) resultDiv.innerHTML = '<div class="index-result err">请求失败: ' + e.message + '</div>';
    if (btn) { btn.disabled = false; btn.textContent = '重建索引'; }
  }
}

/* ==================== 右侧面板切换 ==================== */

function switchSideTab(tab) {
  document.querySelectorAll('.side-tab-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
  });
  document.querySelectorAll('.side-panel').forEach(function(panel) {
    panel.classList.remove('active');
  });
  var panel = document.getElementById('sidePanel' + tab.charAt(0).toUpperCase() + tab.slice(1));
  if (panel) panel.classList.add('active');
  if (tab === 'settings') loadWikiSettingsData();
  if (tab === 'ops') restoreIndexProgress();
}

/* ==================== 设置管理 ==================== */

async function loadWikiSettingsData() {
  try {
    _wikiConfig = await fetchJson(API + '/wiki/settings');
  } catch (e) {
    console.error('[wiki] loadWikiSettingsData error:', e);
  }
  fillSettingsForm(_wikiConfig || {});
}

function fillSettingsForm(data) {
  if (data.error) return;
  var el;
  el = document.getElementById('wsWikiDir');       if (el) el.value = data.wiki_dir || 'wiki';
  el = document.getElementById('wsLightragDir');   if (el) el.value = data.lightrag_dir || 'rag/lightrag_data';
  el = document.getElementById('wsLanguage');      if (el) el.value = data.language || 'Chinese';
  el = document.getElementById('wsChunkSize');     if (el) el.value = data.chunk_token_size || 1200;
  el = document.getElementById('wsTimeout');       if (el) el.value = data.search_timeout || 30;
}

async function saveWikiSettings() {
  var payload = {
    wiki_dir: document.getElementById('wsWikiDir').value.trim(),
    lightrag_dir: document.getElementById('wsLightragDir').value.trim(),
    language: document.getElementById('wsLanguage').value,
    chunk_token_size: parseInt(document.getElementById('wsChunkSize').value) || 1200,
    search_timeout: parseInt(document.getElementById('wsTimeout').value) || 30,
  };
  try {
    var resp = await fetch(API + '/wiki/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    var data = await resp.json();
    if (data.ok) {
      _wikiConfig = Object.assign({}, _wikiConfig || {}, payload);
      toast('设置已保存');
      await loadWikiData();
    } else {
      alert('保存失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    console.error('[wiki] saveWikiSettings error:', e);
    alert('请求失败: ' + e.message);
  }
}

/* ==================== Cleanup ==================== */

var cleanup;
cleanup = function() {};
