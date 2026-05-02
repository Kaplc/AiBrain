/* 路由 + 页面加载 + 状态栏 */

let currentPage = null;
const pageCache = {};

// ── 前端日志捕获 ──────────────────────────────────────────
const _orig = { log: console.log, info: console.info, warn: console.warn, error: console.error };

function _sendLog(level, args) {
  try {
    const msg = Array.from(args).map(a => {
      if (typeof a === 'object') {
        try { return JSON.stringify(a); } catch { return String(a); }
      }
      return String(a);
    }).join(' ');
    fetch(API + '/log', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ level, message: msg, source: 'frontend' })
    }).catch(() => {});
  } catch {}
}

console.log   = (...a) => { _orig.log.apply(console, a);   _sendLog('info',  a); };
console.info  = (...a) => { _orig.info.apply(console, a);  _sendLog('info',  a); };
console.warn  = (...a) => { _orig.warn.apply(console, a);  _sendLog('warn',  a); };
console.error = (...a) => { _orig.error.apply(console, a); _sendLog('error', a); };

window.onerror = (msg, src, line, col, err) => {
  _sendLog('error', [`${src}:${line}:${col} ${msg}`]);
};
window.onunhandledrejection = (e) => {
  _sendLog('error', [`UnhandledRejection: ${e.reason}`]);
};

// ── 页面加载 ──────────────────────────────────────────────
let _currentScript = null;
let _loadVersion = 0;  // 页面版本号，用于检测过期回调

async function loadPage(page, force = false) {
  console.log('[router] loadPage start', page, {force, currentPage});
  if (typeof cleanup === 'function') cleanup();
  if (currentPage === page && !force) {
    console.log('[router] loadPage skipped (same page, no force)');
    return;
  }

  const content = document.getElementById('page-content');
  if (!pageCache[page]) {
    try {
      console.log('[router] fetching HTML:', page);
      const resp = await fetch(`modules/${page}/${page}.html`);
      pageCache[page] = await resp.text();
      console.log('[router] HTML cached:', page);
    } catch(e) {
      console.error('[router] fetch HTML failed:', e);
      content.innerHTML = `<div style="padding:24px;color:#ef4444">加载失败: ${page}</div>`;
      return;
    }
  }

  console.log('[router] rendering page:', page);
  content.innerHTML = pageCache[page];

  // 递增版本号，使旧脚本的 onload 回调失效
  const thisVersion = ++_loadVersion;

  // 解析 HTML 片段依赖（data-deps="header.html,stats.html"）
  // 每个片段会被 fetch 后塞入 <div id="slot-{name}"> 占位符
  const depMeta = content.querySelector('[data-deps]');
  const allFragments = depMeta ? depMeta.getAttribute('data-deps').split(',').filter(Boolean) : [];
  const htmlFrags = allFragments.filter(f => f.endsWith('.html'));
  const jsFrags = allFragments.filter(f => !f.endsWith('.html'));

  // 清理旧脚本
  if (_currentScript) { _currentScript.remove(); _currentScript = null; }

  // 加载所有 HTML 片段，并行 fetch，串行塞入 slot
  async function loadHtmlFragments() {
    // 并行 fetch 所有片段
    const results = await Promise.all(htmlFrags.map(f =>
      fetch(`modules/${page}/${f}`).then(r => r.text()).catch(() => '')
    ));
    // 串行塞入 slot
    // wiki_stats.html → slot-stats, wiki_ops.html → slot-ops, wiki_settings.html → slot-settings
    const slotMap = {
      'wiki_stats': 'stats',
      'wiki_ops': 'ops',
      'wiki_settings': 'settings',
    };
    for (let i = 0; i < htmlFrags.length; i++) {
      const slotKey = htmlFrags[i].replace('.html', '');
      const slotId = 'slot-' + (slotMap[slotKey] || slotKey);
      const slot = document.getElementById(slotId);
      if (slot) slot.innerHTML = results[i];
    }
    // HTML 片段加载完毕，开始加载 JS
    loadScripts(0);
  }

  const allScripts = jsFrags.map(d => d.endsWith('.js') ? d : d + '.js').concat(`${page}.js`);
  function loadScripts(index) {
    if (index >= allScripts.length) {
      if (thisVersion !== _loadVersion) {
        return;
      }
      setTimeout(() => { if (typeof onPageLoad === 'function') onPageLoad(); }, 0);
      return;
    }
    const script = document.createElement('script');
    script.src = `modules/${page}/${allScripts[index]}?_t=${Date.now()}`;
    script.onload = () => loadScripts(index + 1);
    document.body.appendChild(script);
    if (index === 0) _currentScript = script;
  }

  loadHtmlFragments();

  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');
  currentPage = page;
  console.log('[router] loadPage done', page);
}

// ── 共享状态 UI 更新 ───────────────────────────────────────
function updateStatusUI(d) {
  const dotEl = document.getElementById('statusDot');
  if (dotEl) {
    const target = 'status-dot' + (d.model_loaded ? ' ready' : '');
    if (dotEl.className !== target) dotEl.className = target;
  }

  const sbDot = document.getElementById('sbModelDot');
  const sbText = document.getElementById('sbModelText');
  const sbDevice = document.getElementById('sbDeviceText');
  if (sbDot && sbText) {
    if (d.model_loaded) {
      if (sbDot.className !== 'statusbar-dot ok') sbDot.className = 'statusbar-dot ok';
      if (sbText.textContent !== '模型就绪') sbText.textContent = '模型就绪';
    } else {
      if (sbDot.className !== 'statusbar-dot loading') sbDot.className = 'statusbar-dot loading';
      if (sbText.textContent !== '模型加载中') sbText.textContent = '模型加载中';
    }
  }
  if (sbDevice) {
    const map = {cuda: 'GPU', cpu: 'CPU'};
    const target = map[d.device] || d.device || 'CPU';
    if (sbDevice.textContent !== target) sbDevice.textContent = target;
  }
}

// ── 状态检查轮询 ────────────────────────────────────────────
let _lastModelLoaded = false;

async function checkStatus(retries = 3) {
  try {
    const d = await fetch(API + '/status').then(r => r.json());
    updateStatusUI(d);
    _lastModelLoaded = d.model_loaded;
  } catch {
    if (retries > 0) { setTimeout(() => checkStatus(retries - 1), 1000); return; }

    const dotEl = document.getElementById('statusDot');
    if (dotEl) dotEl.className = 'status-dot';
    const sbDot = document.getElementById('sbModelDot');
    const sbText = document.getElementById('sbModelText');
    if (sbDot) sbDot.className = 'statusbar-dot err';
    if (sbText) sbText.textContent = '未连接';
  }
  setTimeout(checkStatus, 3000);
}

// Init
checkStatus();
loadPage('overview');
