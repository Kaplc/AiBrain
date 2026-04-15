/* 路由 + 共享工具 */

const API = 'http://127.0.0.1:18765';
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

async function loadPage(page, force = false) {
  // 切换页面时清理上一个页面的资源
  if (typeof cleanup === 'function') cleanup();
  if (currentPage === page && !force) return;

  const content = document.getElementById('page-content');
  if (!pageCache[page]) {
    try {
      const resp = await fetch(`modules/${page}/${page}.html`);
      pageCache[page] = await resp.text();
    } catch(e) {
      content.innerHTML = `<div style="padding:24px;color:#ef4444">加载失败: ${page}</div>`;
      return;
    }
  }

  content.innerHTML = pageCache[page];

  // 移除旧脚本避免变量重复声明
  if (_currentScript) {
    _currentScript.remove();
    _currentScript = null;
  }

  // 加载页面 JS
  const script = document.createElement('script');
  script.src = `modules/${page}/${page}.js?_t=${Date.now()}`;
  script.onload = () => {
    if (typeof onPageLoad === 'function') onPageLoad();
  };
  document.body.appendChild(script);
  _currentScript = script;

  // 更新导航
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');
  currentPage = page;
}

// ── Toast ─────────────────────────────────────────────────
document.body.insertAdjacentHTML('beforeend', `<div class="toast" id="toast"></div>`);

function toast(msg, type='success') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast show ' + type;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = 'toast', 2800);
}

// ── 共享状态 ──────────────────────────────────────────────
function updateStatusUI(d) {
  const dotEl = document.getElementById('statusDot');
  if (dotEl) dotEl.className = 'status-dot' + (d.model_loaded ? ' ready' : '');

  const sbDot = document.getElementById('sbModelDot');
  const sbText = document.getElementById('sbModelText');
  const sbDevice = document.getElementById('sbDeviceText');
  if (sbDot && sbText) {
    if (d.model_loaded) {
      sbDot.className = 'statusbar-dot ok';
      sbText.textContent = '模型就绪';
    } else {
      sbDot.className = 'statusbar-dot loading';
      sbText.textContent = '模型加载中';
    }
  }
  if (sbDevice) {
    const map = {cuda: 'GPU', cpu: 'CPU'};
    sbDevice.textContent = map[d.device] || d.device || 'CPU';
  }
}

// ── 状态检查 ──────────────────────────────────────────────
let _lastModelLoaded = false;

async function checkStatus(retries = 3) {
  try {
    const d = await fetch(API + '/status').then(r => r.json());
    updateStatusUI(d);
    // 模型从 false 变成 true 时，强制刷新 overview 页面
    if (!_lastModelLoaded && d.model_loaded && currentPage === 'overview') {
      loadPage('overview', true);
    }
    _lastModelLoaded = d.model_loaded;
    if (!d.model_loaded) setTimeout(checkStatus, 3000);
  } catch {
    if (retries > 0) {
      setTimeout(() => checkStatus(retries - 1), 1000);
      return;
    }
    const dotEl = document.getElementById('statusDot');
    if (dotEl) dotEl.className = 'status-dot';
    const sbDot = document.getElementById('sbModelDot');
    const sbText = document.getElementById('sbModelText');
    if (sbDot) sbDot.className = 'statusbar-dot err';
    if (sbText) sbText.textContent = '未连接';
    setTimeout(checkStatus, 3000);
  }
}

// Init
checkStatus();
loadPage('overview');
