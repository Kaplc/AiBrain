/* 设置页面 */
var pendingDevice = 'cpu';
var savedDevice = 'cpu';

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
    const [cfg, st] = await Promise.all([
      fetch(API + '/settings').then(r => r.json()),
      fetch(API + '/status').then(r => r.json()),
    ]);

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
      } else {
        gpuEl.textContent = '❌ 未检测到 NVIDIA GPU，GPU 选项不可用';
        gpuEl.className = 'gpu-info err';
      }
    }
  } catch {}
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
