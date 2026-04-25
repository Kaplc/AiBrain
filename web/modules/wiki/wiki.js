/* Wiki 状态页面 */

var _wikiFiles = [];
var _sortKey = 'modified';
var _sortAsc = false;
var _wikiConfig = null;

function escHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function onPageLoad() {
  loadWikiConfig().then(function() { loadWikiData(); });
}

async function loadWikiConfig() {
  try {
    _wikiConfig = await fetchJson(API + '/wiki/settings');
  } catch (e) {
    console.error('[wiki] loadWikiConfig error:', e);
    _wikiConfig = {};
  }
}

async function loadWikiData() {
  var wrap = document.getElementById('wikiTableWrap');
  if (wrap) wrap.innerHTML = '<div class="mini-loading"></div>';
  document.getElementById('indexResult').innerHTML = '';

  try {
    var data = await fetchJson(API + '/wiki/list');
    _wikiFiles = Array.isArray(data.files) ? data.files : [];

    document.getElementById('wikiFileCount').textContent = _wikiFiles.length;

    var totalBytes = 0;
    _wikiFiles.forEach(function(f) { totalBytes += f.size_bytes || 0; });
    document.getElementById('wikiTotalSize').textContent = formatSize(totalBytes);
    document.getElementById('wikiSizeSub').textContent = _wikiFiles.length + ' 个 .md 文件';

    if (_wikiFiles.length === 0) {
      document.getElementById('wikiFileCount').textContent = '0';
      wrap.innerHTML = '<div class="empty-state">Wiki 目录为空</div>';
      return;
    }

    renderTable(_wikiFiles);
    document.getElementById('wikiFileListMeta').textContent = _wikiFiles.length + ' 个文件';
    document.getElementById('wikiStatus').textContent = '就绪';
    document.getElementById('wikiStatus').style.color = '#86efac';
  } catch (e) {
    console.error('[wiki] loadWikiData error:', e);
    var w2 = document.getElementById('wikiTableWrap');
    if (w2) w2.innerHTML = '<div class="empty-state">加载失败，请检查后端连接</div>';
    document.getElementById('wikiStatus').textContent = '异常';
    document.getElementById('wikiStatus').style.color = '#fca5a5';
  }
}

async function loadLog() {
  var wrap = document.getElementById('wikiLogWrap');
  if (wrap) wrap.innerHTML = '<div class="mini-loading"></div>';

  try {
    var data = await fetchJson(API + '/wiki/log?lines=200', 3);
    if (!data.lines) {
      wrap.innerHTML = '<div class="empty-state">' + (data.error || '无日志') + '</div>';
      return;
    }

    var metaEl = document.getElementById('wikiLogMeta');
    if (metaEl && data.file) {
      metaEl.textContent = data.file + ' | 共 ' + data.total_relevant + ' 条，显示 ' + data.returned + ' 条';
    }

    var html = '';
    data.lines.forEach(function(line) {
      var cls = '';
      var display = escHtml(line);

      var m = line.match(/^\[([^\]]+)\]\s+\[(INFO|WARNING|ERROR|WARN)\]/i);
      if (m) {
        var lvl = m[2].toLowerCase();
        if (lvl.indexOf('error') >= 0) cls = 'log-level-error';
        else if (lvl.indexOf('warn') >= 0) cls = 'log-level-warn';
        else cls = 'log-level-info';
        display = '<span class="log-time">' + escHtml(m[1]) + '</span> <span class="' + cls + '">[' + m[2] + ']</span>' + escHtml(line.substring(m[0].length));
      } else if (/^\d{4}-\d{2}\/\d{2}\//.test(line)) {
        cls = 'log-level-info';
      } else if (/(?:error|fail|Exception)/i.test(line)) {
        cls = 'log-level-error';
      } else if (/warn|timeout|降级/i.test(line)) {
        cls = 'log-level-warn';
      } else if (/\[(RAG|API)[→←⚠✗]\]/i.test(line)) {
        cls = 'log-level-info';
      }

      html += '<div class="log-line ' + cls + '">' + display + '</div>';
    });

    wrap.innerHTML = html || '<div class="empty-state">无相关日志</div>';
    wrap.scrollTop = wrap.scrollHeight;
  } catch (e) {
    console.error('[wiki] loadLog error:', e);
    if (wrap) wrap.innerHTML = '<div class="empty-state">日志加载失败: ' + e.message + '</div>';
  }
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

function sortFiles(key) {
  if (_sortKey === key) { _sortAsc = !_sortAsc; } else { _sortKey = key; _sortAsc = true; }
  _wikiFiles.sort(function(a, b) {
    var va = a[key], vb = b[key];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return _sortAsc ? -1 : 1;
    if (va > vb) return _sortAsc ? 1 : -1;
    return 0;
  });
  renderTable(_wikiFiles);
}

function copyPath(path, row) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(path).then(function() {
      showCopyToast(row);
    });
  } else {
    var ta = document.createElement('textarea');
    ta.value = path;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showCopyToast(row);
  }
}

function showCopyToast(row) {
  var existing = document.querySelector('.copy-toast');
  if (existing) existing.remove();
  var toast = document.createElement('div');
  toast.className = 'copy-toast';
  toast.textContent = '路径已复制';
  document.body.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 1200);
}

function renderTable(files) {
  var wrap = document.getElementById('wikiTableWrap');
  if (!wrap || !files.length) return;

  var arrow = function(key) {
    if (_sortKey !== key) return '';
    return _sortAsc ? ' \u25B2' : ' \u25BC';
  };

  var html = '<table class="file-table"><thead><tr>'
           + '<th onclick="sortFiles(\'filename\')">文件名' + arrow('filename') + '</th>'
           + '<th onclick="sortFiles(\'size_bytes\')">大小' + arrow('size_bytes') + '</th>'
           + '<th onclick="sortFiles(\'modified\')">修改时间' + arrow('modified') + '</th>'
           + '<th>预览</th></tr></thead><tbody>';

  files.forEach(function(f) {
    html += '<tr onclick="copyPath(\'' + escAttr(f.abs_path || f.filename) + '\', this)" style="cursor:pointer">'
         + '<td class="ft-name">' + escHtml(f.filename) + '</td>'
         + '<td class="ft-meta">' + formatSize(f.size_bytes) + '</td>'
         + '<td class="ft-meta">' + formatDate(f.modified) + '</td>'
         + '<td class="ft-preview" title="' + escAttr(f.preview) + '">' + escHtml(f.preview || '') + '</td>'
         + '</tr>';
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}

async function rebuildIndex() {
  var btn = document.getElementById('btnReindex');
  var resultDiv = document.getElementById('indexResult');
  btn.disabled = true;
  btn.textContent = '索引中...';
  resultDiv.innerHTML = '';

  try {
    var resp = await fetch(API + '/wiki/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!resp.ok) throw new Error('HTTP ' + resp.status);

    var data = await resp.json();

    if (data.error) {
      resultDiv.innerHTML = '<div class="index-result err">索引失败: ' + escHtml(data.error) + '</div>';
    } else {
      var parts = [];
      if (data.added && data.added.length) parts.push('新增: ' + data.added.join(', '));
      if (data.updated && data.updated.length) parts.push('更新: ' + data.updated.join(', '));
      if (data.deleted && data.deleted.length) parts.push('移除: ' + data.deleted.join(', '));
      if (data.unchanged) parts.push('未变: ' + data.unchanged + ' 个');
      if (data.errors && data.errors.length) parts.push('错误: ' + data.errors.join('; '));

      resultDiv.innerHTML = '<div class="index-result ok">' + (parts.join('<br>') || '完成') + '</div>';

      await loadWikiData();
    }
  } catch (e) {
    console.error('[wiki] rebuildIndex error:', e);
    resultDiv.innerHTML = '<div class="index-result err">请求失败: ' + e.message + '</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = '重建索引';
  }
}

/* Wiki Settings */
function openWikiSettings() {
  loadWikiSettingsData();
  document.getElementById('wikiSettingsModal').classList.add('show');
}

function closeWikiSettings() {
  document.getElementById('wikiSettingsModal').classList.remove('show');
}

async function loadWikiSettingsData() {
  try {
    var data = await fetchJson(API + '/wiki/settings');
    _wikiConfig = data;
  } catch (e) {
    console.error('[wiki] loadWikiSettingsData error:', e);
  }
  fillSettingsForm(_wikiConfig || {});
}

function fillSettingsForm(data) {
  if (data.error) return;
  document.getElementById('wsWikiDir').value = data.wiki_dir || 'wiki';
  document.getElementById('wsLightragDir').value = data.lightrag_dir || 'rag/lightrag_data';
  document.getElementById('wsLanguage').value = data.language || 'Chinese';
  document.getElementById('wsChunkSize').value = data.chunk_token_size || 1200;
  document.getElementById('wsTimeout').value = data.search_timeout || 30;
  if (data.llm) {
    document.getElementById('wsLlmProvider').value = data.llm.provider || '';
    document.getElementById('wsLlmModel').value = data.llm.model || '';
    document.getElementById('wsLlmBaseUrl').value = data.llm.base_url || '';
    var keyEl = document.getElementById('wsLlmApiKey');
    if (data.llm.api_key === '****') {
      keyEl.placeholder = '已配置（留空不修改）';
      keyEl.value = '';
    } else if (data.llm.api_key) {
        keyEl.placeholder = '已配置';
        keyEl.value = '';
      } else {
        keyEl.placeholder = '留空则不修改';
      }
    }
}

async function saveWikiSettings() {
  var payload = {
    wiki_dir: document.getElementById('wsWikiDir').value.trim(),
    lightrag_dir: document.getElementById('wsLightragDir').value.trim(),
    language: document.getElementById('wsLanguage').value,
    chunk_token_size: parseInt(document.getElementById('wsChunkSize').value) || 1200,
    search_timeout: parseInt(document.getElementById('wsTimeout').value) || 30,
    llm: {
      provider: document.getElementById('wsLlmProvider').value,
      model: document.getElementById('wsLlmModel').value.trim(),
      api_key: document.getElementById('wsLlmApiKey').value.trim(),
      base_url: document.getElementById('wsLlmBaseUrl').value.trim(),
    },
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
      closeWikiSettings();
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

/* Cleanup */
var cleanup;

cleanup = function() {};
