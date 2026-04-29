/* 总览页面 */
var _overviewTimer = null;
var _sysInfoTimer = null;
var _currentChartRange = 'today';
var _resizeTimer = null;

function onPageLoad() {
  console.log('[overview] onPageLoad start');
  // 立即加载图表和记忆总数（不等待模型）
  console.log('[overview] fetching chart and memory count');
  fetchAndDrawChart(_currentChartRange);
  fetchMemoryCount();

  // 加载页面数据
  console.log('[overview] loading overview page data');
  loadOverviewPage();

  // 模型 & Qdrant 状态轮询（1秒，两者都就绪后停止）
  if (_overviewTimer) clearInterval(_overviewTimer);
  _overviewTimer = setInterval(async () => {
    try {
      // 守卫：overview 页面可能已被切换
      if (!document.getElementById('scModelValue')) return;
      const st = await fetch(API + '/status').then(r => r.json());
      const modelValue = document.getElementById('scModelValue');
      const modelSub = document.getElementById('scModelSub');
      const modelBadge = document.getElementById('scModelBadge');
      const qBadge = document.getElementById('scQdrantBadge');

      // 更新 Qdrant badge
      if (qBadge) {
        if (st.qdrant_ready) { qBadge.textContent = 'OK'; qBadge.className = 'sc-badge green'; }
        else { qBadge.textContent = 'ERR'; qBadge.className = 'sc-badge red'; }
      }

      if (st.model_loaded) {
        if (modelValue) modelValue.innerHTML = '';
        if (modelSub) {
          const name = st.embedding_model || 'bge-m3';
          const size = st.model_size || '';
          modelSub.innerHTML = `${name} ${size}`;
        }
        if (modelBadge) { modelBadge.textContent = 'OK'; modelBadge.className = 'sc-badge green'; }
        // 两者都就绪才停止轮询
        if (st.qdrant_ready && _overviewTimer) { clearInterval(_overviewTimer); _overviewTimer = null; }
      }
    } catch {}
  }, 1000);

  // 系统信息轮询（1秒）
  if (_sysInfoTimer) clearInterval(_sysInfoTimer);
  _sysInfoTimer = setInterval(async () => {
    try {
      // 守卫：overview 页面可能已被切换
      if (!document.getElementById('scDeviceSub1')) return;
      const sysInfo = await fetchJson(API + '/system-info');
      updateDeviceCard(sysInfo);
    } catch {}
  }, 1000);

  // 图表 tab 切换
  const tabsEl = document.getElementById('chartTabs');
  if (tabsEl) {
    tabsEl.addEventListener('click', async (e) => {
      const btn = e.target.closest('.chart-tab');
      if (!btn) return;
      const range = btn.dataset.range;
      if (!range || range === _currentChartRange) return;
      _currentChartRange = range;
      tabsEl.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      console.log('[overview] chart tab changed, fetching range:', range);
      await fetchAndDrawChart(range);
    });
  }
  console.log('[overview] onPageLoad done');
}

function cleanup() {
  if (_overviewTimer) { clearInterval(_overviewTimer); _overviewTimer = null; }
  if (_sysInfoTimer) { clearInterval(_sysInfoTimer); _sysInfoTimer = null; }
  if (_resizeTimer) { clearTimeout(_resizeTimer); _resizeTimer = null; }
}

function updateDeviceCard(sysInfo) {
  const devSub1 = document.getElementById('scDeviceSub1');
  const devSub2 = document.getElementById('scDeviceSub2');
  const devSub2b = document.getElementById('scDeviceSub2b');
  const devSub3 = document.getElementById('scDeviceSub3');
  const devSub4 = document.getElementById('scDeviceSub4');
  const devSub5 = document.getElementById('scDeviceSub5');
  const devSub6 = document.getElementById('scDeviceSub6');
  if (!devSub1 || !sysInfo) return;

  // 1. 系统信息
  const plat = (sysInfo.platform || '').substring(0, 50);
  if (devSub1) devSub1.textContent = plat;

  // 2. CPU
  if (devSub2) devSub2.textContent = `CPU ${(sysInfo.cpu_percent||0).toFixed(0)}%`;

  // 2b. CPU 温度
  if (devSub2b) devSub2b.textContent = sysInfo.cpu_temperature != null ? `CPU温度 ${sysInfo.cpu_temperature}°C` : '';

  // 3. 内存大小
  const sysMemTotal = sysInfo.memory_total / (1024**3);
  const sysMemUsed = sysInfo.memory_used / (1024**3);
  if (devSub3) devSub3.textContent = `内存 ${sysMemUsed.toFixed(1)}/${sysMemTotal.toFixed(1)}GB ${sysInfo.memory_percent.toFixed(0)}%`;

  // 4-6. GPU
  if (sysInfo.gpu) {
    const g = sysInfo.gpu;
    const gpuMemTotal = g.memory_total / (1024**3);
    const gpuMemUsed = g.memory_used / (1024**3);
    if (devSub4) devSub4.textContent = `GPU ${g.name}`;
    if (devSub5) devSub5.textContent = `显存 ${gpuMemUsed.toFixed(1)}/${gpuMemTotal.toFixed(1)}GB ${g.memory_percent}%`;
    if (devSub6) devSub6.textContent = g.temperature != null ? `GPU温度 ${g.temperature}°C` : '';
  } else {
    [devSub4, devSub5, devSub6].forEach(el => { if (el) el.textContent = ''; });
  }
}

async function loadOverviewPage() {
  // 页面切换守卫：如果 overview 容器已不存在，直接返回
  if (!document.getElementById('chartContainer')) return;
  console.log('[overview] loadOverviewPage start');
  try {
    const [cfg, st, sysInfo] = await Promise.all([
      fetchJson(API + '/settings'),
      fetchJson(API + '/status'),
      fetchJson(API + '/system-info'),
    ]);
    console.log('[overview] settings/status/sysinfo loaded', {cfg_exists: !!cfg, st_model_loaded: st.model_loaded});

    // Model status
    const modelValue = document.getElementById('scModelValue');
    const modelSub = document.getElementById('scModelSub');
    const modelBadge = document.getElementById('scModelBadge');
    if (st.model_loaded) {
      if (modelValue) modelValue.innerHTML = '';
      if (modelBadge) { modelBadge.textContent = 'OK'; modelBadge.className = 'sc-badge green'; }
      if (modelSub) {
        const name = st.embedding_model || 'bge-m3';
        const size = st.model_size || '';
        modelSub.innerHTML = `${name} ${size}`;
      }
    } else {
      if (modelValue) modelValue.innerHTML = '';
      if (modelBadge) { modelBadge.textContent = ''; modelBadge.className = 'sc-badge'; }
      if (modelSub) modelSub.innerHTML = '<div style="text-align:center"><span class="mini-loading"></span><div style="font-size:11px;color:#64748b;margin-top:4px"><span class="sc-badge yellow">加载中</span></div></div>';
    }

    // Qdrant
    const qBadge = document.getElementById('scQdrantBadge');
    if (qBadge) {
      if (st.qdrant_ready) { qBadge.textContent = 'OK'; qBadge.className = 'sc-badge green'; }
      else { qBadge.textContent = 'ERR'; qBadge.className = 'sc-badge red'; }
    }
    const qHostPortSub = document.getElementById('scQdrantHostPortSub');
    const qCollectionSub = document.getElementById('scQdrantCollectionSub');
    const qStorageSub = document.getElementById('scQdrantStorageSub');
    const qTopKSub = document.getElementById('scQdrantTopKSub');
    const qDimSub = document.getElementById('scDimSub');
    if (qHostPortSub) qHostPortSub.textContent = `${st.qdrant_host || 'localhost'}:${st.qdrant_port || 6333}`;
    if (qCollectionSub) qCollectionSub.textContent = `Collection: ${st.qdrant_collection || 'memories'}`;
    if (qStorageSub) qStorageSub.textContent = `存储: ${st.qdrant_storage_path || 'storage'}`;
    if (qTopKSub) qTopKSub.textContent = `Top-K: ${st.qdrant_top_k || 5}`;
    if (qDimSub) qDimSub.textContent = `维度: ${st.embedding_dim || 1024}`;
    const qDiskSizeSub = document.getElementById('scQdrantDiskSizeSub');
    // 显示磁盘大小（如果 qStorageSub 不存在则用 disk size）
    const diskSize = st.qdrant_disk_size || 0;
    if (qDiskSizeSub) {
      let sizeStr = '';
      if (diskSize >= 1024 * 1024 * 1024) {
        sizeStr = `${(diskSize / (1024 * 1024 * 1024)).toFixed(2)} GB`;
      } else if (diskSize >= 1024 * 1024) {
        sizeStr = `${(diskSize / (1024 * 1024)).toFixed(1)} MB`;
      } else if (diskSize >= 1024) {
        sizeStr = `${(diskSize / 1024).toFixed(1)} KB`;
      } else if (diskSize > 0) {
        sizeStr = `${diskSize} B`;
      } else {
        sizeStr = '0 B';
      }
      qDiskSizeSub.textContent = sizeStr;
    }

    // Device info
    const devSub1 = document.getElementById('scDeviceSub1');
    const devSub2 = document.getElementById('scDeviceSub2');
    const devSub2b = document.getElementById('scDeviceSub2b');
    const devSub3 = document.getElementById('scDeviceSub3');
    const devSub4 = document.getElementById('scDeviceSub4');
    const devSub5 = document.getElementById('scDeviceSub5');
    const devSub6 = document.getElementById('scDeviceSub6');

    // 1. 系统信息
    const plat = (sysInfo.platform || '').substring(0, 50);
    if (devSub1) devSub1.textContent = plat;

    // 2. CPU
    const cpuPct = sysInfo.cpu_percent;
    if (devSub2) devSub2.textContent = `CPU ${(sysInfo.cpu_percent||0).toFixed(0)}%`;

    // 2b. CPU 温度
    if (devSub2b) devSub2b.textContent = sysInfo.cpu_temperature != null ? `CPU温度 ${sysInfo.cpu_temperature}°C` : '';

    // 3. 内存大小
    const sysMemTotal = sysInfo.memory_total / (1024**3);
    const sysMemUsed = sysInfo.memory_used / (1024**3);
    if (devSub3) devSub3.textContent = `内存 ${sysMemUsed.toFixed(1)}/${sysMemTotal.toFixed(1)}GB ${sysInfo.memory_percent.toFixed(0)}%`;

    // 4-6. GPU
    if (sysInfo.gpu) {
      const g = sysInfo.gpu;
      const gpuMemTotal = g.memory_total / (1024**3);
      const gpuMemUsed = g.memory_used / (1024**3);
      if (devSub4) devSub4.textContent = `GPU ${g.name}`;
      if (devSub5) devSub5.textContent = `显存 ${gpuMemUsed.toFixed(1)}/${gpuMemTotal.toFixed(1)}GB ${g.memory_percent}%`;
      if (devSub6) devSub6.textContent = g.temperature != null ? `GPU温度 ${g.temperature}°C` : '';
    } else {
      [devSub4, devSub5, devSub6].forEach(el => { if (el) el.textContent = ''; });
    }

    // Stats & chart（已在上层立即触发，这里不再重复调用）
    // 记忆总数已在上层立即加载，无需重复请求


  } catch(e) { console.error('[overview] load failed:', e && e.message ? e.message : String(e)); }
}

// ── 图表 ───────────────────────────────────────────────────

var _chartInstance = null;
var _chartData = null;  // 存储原始数据供 tooltip 使用

function initChart() {
  const container = document.getElementById('chartContainer');
  if (!container) return;
  _chartInstance = echarts.init(container, null, { renderer: 'canvas' });
}

function drawEChart(data, range) {
  if (!_chartInstance) initChart();
  if (!_chartInstance) return;

  // 保存原始数据供 tooltip 使用
  _chartData = data;

  const chartData = data;

  const dates = chartData.map(d => {
    if (range === 'today') return d.date;
    const day = d.date.slice(-2);
    if (day === '01') return d.date.slice(5, 7) + '月';
    return day;
  });

  const option = {
    grid: { top: 8, right: 52, bottom: 24, left: 8 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#2d3149' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      position: 'right',
      splitLine: { lineStyle: { color: '#2d314922' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1e293b',
      borderColor: '#475569',
      borderWidth: 1,
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: function(params) {
        // 使用原始数据中的完整日期
        const rawData = _chartData ? _chartData[params[0].dataIndex] : null;
        const fullDate = rawData ? rawData.date : params[0].axisValue;
        let html = '<div style="font-weight:600;color:#a78bfa;margin-bottom:6px">' + fullDate + '</div>';
        params.forEach(p => {
          const colors = { '累计': '#a78bfa', '新增': '#86efac' };
          html += '<div style="display:flex;justify-content:space-between;gap:12px;margin:2px 0"><span style="color:#94a3b8">' + p.seriesName + '</span><span style="font-weight:600;color:' + (colors[p.seriesName] || '#fff') + '">' + p.value + '</span></div>';
        });
        return html;
      }
    },
    series: [
      {
        name: '新增',
        type: 'line',
        data: range === 'all' ? [] : chartData.map(d => d.added || 0),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#22c55e', width: 2 },
        itemStyle: { color: '#22c55e' },
      },
      {
        name: '累计',
        type: 'line',
        data: chartData.map(d => d.total),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#7c3aed', width: 2 },
        itemStyle: { color: '#7c3aed' },
      },
    ],
  };

  _chartInstance.setOption(option);
}

// 添加窗口大小变化监听
window.addEventListener('resize', () => {
  if (_resizeTimer) clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    if (_chartInstance) _chartInstance.resize();
  }, 250);
});

async function fetchAndDrawChart(range) {
  console.log('[overview] fetchAndDrawChart start', range);
  try {
    const res = await fetchJson(API + '/chart-data?range=' + range);
    // 页面切换守卫：DOM 已被替换则跳过
    if (!document.getElementById('chartContainer')) return;
    console.log('[overview] chart data received', res.data ? res.data.length + ' points' : 'no data');
    const rawData = res.data || [];
    const data = rawData;

    // 图表用的 total 改为从当前范围起点开始的增量累计
    let running = 0;
    data.forEach(d => {
      running += d.added || 0;
      d.total = running;
    });

    // 更新时间段统计（取图表最后一个点的增量累计，即24h/7d/30d新增总数）
    const statEl = document.getElementById('statToday');
    const statLabel = document.getElementById('statLabel');
    if (range === 'all') {
      // 全部页签只显示记忆总数，隐藏增量统计，居中显示
      if (statEl) statEl.style.display = 'none';
      if (statLabel) statLabel.style.display = 'none';
      const chartStats = document.querySelector('.chart-stats');
      if (chartStats) chartStats.classList.add('single');
    } else {
      const chartStats = document.querySelector('.chart-stats');
      if (chartStats) chartStats.classList.remove('single');
      if (statEl) statEl.style.display = '';
      if (statLabel) statLabel.style.display = '';
      if (statEl) {
        const lastTotal = data.length > 0 ? data[data.length - 1].total : 0;
        statEl.textContent = lastTotal;
      }
      if (statLabel) {
        const labels = { 'today': '24h新增', 'week': '7天新增', 'month': '30天新增' };
        statLabel.textContent = labels[range] || '累计';
      }
    }

    drawEChart(data, range);
  } catch(e) { console.error('[overview] chart error:', e); }
}

/* ==================== 数字递增动画 ==================== */
function animateCount(el, target) {
  const current = parseInt(el.textContent) || 0;
  if (current === target) return;
  const diff = target - current;
  const step = Math.max(1, Math.ceil(Math.abs(diff) / 10));
  const interval = setInterval(() => {
    const now = parseInt(el.textContent) || 0;
    const delta = target > now ? Math.min(step, target - now) : Math.max(-step, target - now);
    if (now === target || (delta > 0 ? now >= target : now <= target)) {
      el.textContent = target;
      clearInterval(interval);
    } else {
      el.textContent = now + delta;
    }
  }, 50);
}

/* ==================== 加载记忆总数 ==================== */
async function fetchMemoryCount() {
  console.log('[overview] fetchMemoryCount start');
  try {
    const res = await fetchJson(API + '/memory-count');
    const statTotal = document.getElementById('statTotal');
    if (statTotal) animateCount(statTotal, res.count || 0);
    console.log('[overview] memory count:', res.count);
  } catch (e) {
    console.error('[overview] memory count error:', e);
  }
}
