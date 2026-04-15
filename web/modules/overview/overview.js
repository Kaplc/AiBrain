/* 总览页面 */
var _overviewTimer = null;

function onPageLoad() {
  loadOverviewPage();
  // 每 3 秒刷新一次状态，直到模型就绪
  if (_overviewTimer) clearInterval(_overviewTimer);
  _overviewTimer = setInterval(async () => {
    try {
      const st = await fetch(API + '/status').then(r => r.json());
      const modelValue = document.getElementById('scModelValue');
      const modelSub = document.getElementById('scModelSub');
      if (st.model_loaded) {
        if (modelValue) modelValue.innerHTML = `<span class="mini-loading"></span>`;
        if (modelSub) {
          const name = st.embedding_model || 'bge-m3';
          const size = st.model_size || '';
          modelSub.innerHTML = `<span class="sc-badge green">OK</span> ${name} ${size}`;
        }
        if (_overviewTimer) { clearInterval(_overviewTimer); _overviewTimer = null; }
      }
    } catch {}
  }, 3000);
}

function cleanup() {
  if (_overviewTimer) { clearInterval(_overviewTimer); _overviewTimer = null; }
}

async function fetchJson(url, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(url);
      if (!r.ok && r.status >= 500 && i < retries - 1) {
        await new Promise(res => setTimeout(res, 500));
        continue;
      }
      return await r.json();
    } catch(e) {
      if (i < retries - 1) {
        await new Promise(res => setTimeout(res, 500));
        continue;
      }
      throw e;
    }
  }
}

async function loadOverviewPage() {
  try {
    const [cfg, st, sysInfo] = await Promise.all([
      fetchJson(API + '/settings'),
      fetchJson(API + '/status'),
      fetchJson(API + '/system-info'),
    ]);
    console.log('[overview] cfg:', cfg);
    console.log('[overview] st:', st);
    console.log('[overview] sysInfo:', sysInfo);
    const r = await fetch(API + '/list', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: '{}'
    }).then(r => r.json());
    console.log('[overview] memories count:', (r.memories || []).length);

    // Model status (centered loading, info below)
    const modelValue = document.getElementById('scModelValue');
    const modelSub = document.getElementById('scModelSub');
    if (st.model_loaded) {
      if (modelValue) modelValue.innerHTML = '';
      if (modelSub) {
        const name = st.embedding_model || 'bge-m3';
        const size = st.model_size || '';
        modelSub.innerHTML = `<span class="sc-badge green">OK</span> ${name} ${size}`;
      }
    } else {
      if (modelValue) modelValue.innerHTML = `<span class="mini-loading"></span>`;
      if (modelSub) modelSub.innerHTML = `<span class="sc-badge yellow">加载中</span>`;
    }

    // Qdrant status + dim (badge in label)
    const qBadge = document.getElementById('scQdrantBadge');
    const qDimSub = document.getElementById('scDimSub');
    if (qBadge) {
      if (st.qdrant_ready) {
        qBadge.textContent = 'OK';
        qBadge.className = 'sc-badge green';
      } else {
        qBadge.textContent = 'ERR';
        qBadge.className = 'sc-badge red';
      }
    }
    if (qDimSub) {
      qDimSub.textContent = `向量维度 ${st.embedding_dim || 1024}`;
    }

    // Device status with system/GPU info (vertical layout)
    const devSub1 = document.getElementById('scDeviceSub1');
    const devSub2 = document.getElementById('scDeviceSub2');
    const devSub3 = document.getElementById('scDeviceSub3');
    const devSub4 = document.getElementById('scDeviceSub4');
    const devSub5 = document.getElementById('scDeviceSub5');
    // 系统信息
    const sysMemTotal = sysInfo.memory_total / (1024**3);
    const sysMemUsed = sysInfo.memory_used / (1024**3);
    const sysMemPct = sysInfo.memory_percent;
    const cpuPct = sysInfo.cpu_percent;
    if (devSub1) devSub1.textContent = `系统 ${sysMemUsed.toFixed(1)}/${sysMemTotal.toFixed(1)}GB ${sysMemPct.toFixed(0)}%`;
    if (devSub2) devSub2.textContent = `CPU ${cpuPct.toFixed(0)}%`;
    // GPU信息
    if (sysInfo.gpu) {
      const g = sysInfo.gpu;
      const gpuMemTotal = g.memory_total / (1024**3);
      const gpuMemUsed = g.memory_used / (1024**3);
      const gpuMemPct = g.memory_percent;
      if (devSub3) devSub3.textContent = `GPU ${g.name}`;
      if (devSub4) devSub4.textContent = `显存 ${gpuMemUsed.toFixed(1)}/${gpuMemTotal.toFixed(1)}GB ${gpuMemPct}%`;
      if (g.temperature !== null && g.temperature !== undefined && devSub5) {
        devSub5.textContent = `GPU温度 ${g.temperature}°C`;
      } else if (devSub5) {
        devSub5.textContent = '';
      }
    } else {
      if (devSub3) devSub3.textContent = '';
      if (devSub4) devSub4.textContent = '';
      if (devSub5) devSub5.textContent = '';
    }

    // Stats
    const memories = r.memories || [];
    const today = new Date().toISOString().slice(0, 10);
    const todayCnt = memories.filter(m => (m.timestamp || '').startsWith(today)).length;

    const statTotal = document.getElementById('statTotal');
    const statToday = document.getElementById('statToday');
    const statDim = document.getElementById('statDim');
    console.log('[overview] statTotal:', statTotal, 'statToday:', statToday, 'statDim:', statDim);
    if (statTotal) statTotal.textContent = memories.length;
    if (statToday) statToday.textContent = todayCnt;
    if (statDim) statDim.textContent = st.embedding_dim || 1024;

    // Update chart bars
    updateChart(memories.length, todayCnt);
  } catch(e) { console.error('[overview] load failed:', e && e.message ? e.message : String(e)); }
}

function updateChart(total, today) {
  const chart = document.getElementById('chartBody');
  if (!chart) return;
  const bars = chart.querySelectorAll('.bar-wrap');
  const todayRatio = total > 0 ? today / total : 0;
  bars.forEach((wrap, i) => {
    const totalBar = wrap.querySelector('.bar.total');
    const todayBar = wrap.querySelector('.bar.today');
    if (totalBar) {
      const h = Math.min(100, ((i + 1) / 7) * 100 + 5);
      totalBar.style.height = Math.max(4, h) + '%';
    }
    if (todayBar) {
      const h = i === 6 ? Math.min(100, todayRatio * 100 + 3) : Math.max(4, (i + 1) * 2 + todayRatio * 8);
      todayBar.style.height = h + '%';
    }
  });
}
