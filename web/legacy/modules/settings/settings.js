/* 设置页面 */
var pendingDevice = 'cpu';
var savedDevice = 'cpu';
var aibrainConfig = null;  // 动态配置数据

function onPageLoad() {
  loadSettingsPage();
}

async function api(path, data) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  return r.json();
}

function selectDevice(val) {
  pendingDevice = val;
  const sel = document.getElementById('deviceSelect');
  if (sel) sel.value = val;
}

async function loadSettingsPage() {
  try {
    const [cfg, st, aibrain] = await Promise.all([
      fetch(API + '/settings').then(r => r.json()),
      fetch(API + '/status').then(r => r.json()),
      fetch(API + '/aibrain-config').then(r => r.json()),
    ]);

    aibrainConfig = aibrain;

    savedDevice = cfg.device || 'cpu';
    pendingDevice = savedDevice;

    const sel = document.getElementById('deviceSelect');
    if (sel) sel.value = savedDevice;

    const modelDesc = document.getElementById('modelDesc');
    if (modelDesc) {
      const modelName = st.embedding_model || 'BAAI/bge-m3';
      const dim = st.embedding_dim || 1024;
      modelDesc.textContent = `${modelName} · 向量维度 ${dim}`;
    }

    const gpuEl = document.getElementById('gpuInfo');
    if (gpuEl) {
      if (st.cuda_available) {
        gpuEl.innerHTML = `✅ 检测到 GPU：<strong>${st.gpu_name}</strong>`;
        gpuEl.className = 'gpu-info ok';
      } else if (st.gpu_hardware) {
        gpuEl.innerHTML = `⚠️ 检测到 NVIDIA GPU，但安装的是 CPU 版 PyTorch。<br><small>运行以下命令安装 GPU 版：</small><br><code>pip uninstall torch -y && pip install torch --index-url https://download.pytorch.org/whl/cu124</code>`;
        gpuEl.className = 'gpu-info warn';
      } else {
        gpuEl.textContent = '未检测到 NVIDIA GPU，GPU 选项不可用';
        gpuEl.className = 'gpu-info err';
      }
    }

    // 动态渲染表单
    renderDynamicForms(aibrain);
    // 初始化目录检查
    initDirChecks();
  } catch(e) {
    console.error('loadSettingsPage error:', e);
  }
}

function renderDynamicForms(config) {
  // 渲染 mem0 表单
  const mem0Form = document.getElementById('mem0Form');
  if (mem0Form && config.mem0) {
    mem0Form.innerHTML = renderFields(config.mem0.fields, 'mem0');
  }

  // 渲染 wiki 表单
  const wikiForm = document.getElementById('wikiForm');
  if (wikiForm && config.wiki) {
    wikiForm.innerHTML = renderFields(config.wiki.fields, 'wiki');
  }
}

function renderFields(fields, prefix) {
  return fields.map(f => {
    const inputId = `${prefix}_${f.key}`;
    const isDir = f.type === 'dir';

    if (isDir) {
      return `
      <div class="form-row">
        <label>${f.label}</label>
        <div class="dir-input-wrap">
          <input type="text" id="${inputId}" value="${escHtml(String(f.value ?? ''))}" placeholder="${escHtml(String(f.default ?? ''))}">
          <button type="button" class="dir-browse-btn" onclick="browseDir('${inputId}')">📁</button>
          <span class="dir-status" id="${inputId}_status"></span>
        </div>
      </div>
    `;
    } else {
      return `
      <div class="form-row">
        <label>${f.label}</label>
        <input type="${f.type}" id="${inputId}" value="${escHtml(String(f.value ?? ''))}" placeholder="${escHtml(String(f.default ?? ''))}">
      </div>
    `;
    }
  }).join('');
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getFieldValue(prefix, key) {
  const input = document.getElementById(`${prefix}_${key}`);
  return input ? input.value : '';
}

function setFieldValue(prefix, key, value) {
  const input = document.getElementById(`${prefix}_${key}`);
  if (input) input.value = value;
}

async function applySettings() {
  if (pendingDevice === savedDevice) {
    toast('设置未变更', 'info');
    return;
  }
  const btn = document.getElementById('saveBtn');
  if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }
  try {
    await api('/reload-model', {device: pendingDevice});
    savedDevice = pendingDevice;
    toast(`✅ 已保存并重载模型（${pendingDevice}）`, 'success');
  } catch(e) {
    toast('保存失败: ' + e, 'error');
  }
  if (btn) { btn.disabled = false; btn.textContent = '保存'; }
}

function resetSettings() {
  selectDevice(savedDevice);
  toast('已重置', 'info');
}

function resetMem0Config() {
  if (!aibrainConfig || !aibrainConfig.mem0) return;
  aibrainConfig.mem0.fields.forEach(f => {
    setFieldValue('mem0', f.key, f.default);
  });
  toast('已恢复默认', 'info');
}

function resetWikiConfig() {
  if (!aibrainConfig || !aibrainConfig.wiki) return;
  aibrainConfig.wiki.fields.forEach(f => {
    setFieldValue('wiki', f.key, f.default);
  });
  toast('已恢复默认', 'info');
}

async function saveMem0Config() {
  if (!aibrainConfig || !aibrainConfig.mem0) return;
  const data = {};
  aibrainConfig.mem0.fields.forEach(f => {
    const val = getFieldValue('mem0', f.key);
    // 嵌套字段处理 (如 llm_provider -> {"llm": {"provider": ...}})
    if (f.key.includes('_')) {
      const parts = f.key.split('_', 2);
      if (parts.length === 2) {
        if (!data[parts[0]]) data[parts[0]] = {};
        data[parts[0]][parts[1]] = f.type === 'number' ? (parseInt(val) || 0) : val;
        return;
      }
    }
    data[f.key] = f.type === 'number' ? (parseInt(val) || 0) : val;
  });

  try {
    const r = await api('/save-aibrain-config', { mem0: data });
    if (r.error) {
      toast('保存失败: ' + r.error, 'error');
    } else {
      toast('✅ mem0.json 已保存', 'success');
    }
  } catch(e) {
    toast('保存失败: ' + e, 'error');
  }
}

async function saveWikiConfig() {
  if (!aibrainConfig || !aibrainConfig.wiki) return;
  const data = {};
  aibrainConfig.wiki.fields.forEach(f => {
    const val = getFieldValue('wiki', f.key);
    data[f.key] = f.type === 'number' ? (parseInt(val) || 0) : val;
  });

  try {
    const r = await api('/save-aibrain-config', { wiki: data });
    if (r.error) {
      toast('保存失败: ' + r.error, 'error');
    } else {
      toast('✅ wiki.json 已保存', 'success');
    }
  } catch(e) {
    toast('保存失败: ' + e, 'error');
  }
}

function switchTab(tab) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  const contentEl = document.getElementById('tab-' + tab);
  if (contentEl) contentEl.style.display = 'flex';
  const btn = document.querySelector('.tab-btn[data-tab="' + tab + '"]');
  if (btn) btn.classList.add('active');
}

// 文件夹选择（通过后端API选择文件夹）
async function browseDir(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  try {
    const r = await fetch(API + '/select-directory', { method: 'POST' });
    const data = await r.json();
    if (data.path) {
      input.value = data.path;
      checkDirExists(inputId);
    }
  } catch(e) {
    // 如果后端不支持，使用原生input
    const native = document.createElement('input');
    native.type = 'file';
    native.webkitdirectory = true;
    native.onchange = () => {
      if (native.files && native.files[0]) {
        // 获取相对路径
        const fullPath = native.files[0].webkitRelativePath;
        const basePath = fullPath.split('/')[0];
        input.value = basePath;
        checkDirExists(inputId);
      }
    };
    native.click();
  }
}

// 检查目录是否存在（通过后端API）
async function checkDirExists(inputId) {
  const input = document.getElementById(inputId);
  const statusEl = document.getElementById(inputId + '_status');
  if (!input || !statusEl) return;

  const path = input.value.trim();
  if (!path) {
    statusEl.textContent = '';
    statusEl.className = 'dir-status';
    return;
  }

  try {
    const r = await fetch(API + '/check-path', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path})
    });
    const data = await r.json();
    if (data.exists) {
      statusEl.textContent = '✓';
      statusEl.className = 'dir-status ok';
    } else {
      statusEl.textContent = '✗ 不存在';
      statusEl.className = 'dir-status err';
    }
  } catch(e) {
    statusEl.textContent = '';
  }
}

// 初始化目录检查（表单渲染后调用）
function initDirChecks() {
  if (!aibrainConfig) return;
  [...(aibrainConfig.mem0?.fields || []), ...(aibrainConfig.wiki?.fields || [])]
    .filter(f => f.type === 'dir')
    .forEach(f => {
      const inputId = 'mem0_' + f.key;
      const el = document.getElementById(inputId);
      if (el) {
        el.addEventListener('change', () => checkDirExists(inputId));
        el.addEventListener('blur', () => checkDirExists(inputId));
      }
    });
}
