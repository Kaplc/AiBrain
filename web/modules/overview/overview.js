/* 总览页面 */
var _overviewTimer = null;
var _sysInfoTimer = null;
var _currentChartRange = 'today';
var _resizeTimer = null;

function onPageLoad() {
  loadOverviewPage();
  // 模型加载轮询（3秒）
  if (_overviewTimer) clearInterval(_overviewTimer);
  _overviewTimer = setInterval(async () => {
    try {
      const st = await fetch(API + '/status').then(r => r.json());
      const modelValue = document.getElementById('scModelValue');
      const modelSub = document.getElementById('scModelSub');
      if (st.model_loaded) {
        if (modelValue) modelValue.innerHTML = '';
        if (modelSub) {
          const name = st.embedding_model || 'bge-m3';
          const size = st.model_size || '';
          modelSub.innerHTML = `${name} ${size}`;
        }
        if (_overviewTimer) { clearInterval(_overviewTimer); _overviewTimer = null; }
      }
    } catch {}
  }, 3000);

  // 系统信息轮询（1秒）
  if (_sysInfoTimer) clearInterval(_sysInfoTimer);
  _sysInfoTimer = setInterval(async () => {
    try {
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
      await fetchAndDrawChart(range);
    });
  }
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
  try {
    const [cfg, st, sysInfo] = await Promise.all([
      fetchJson(API + '/settings'),
      fetchJson(API + '/status'),
      fetchJson(API + '/system-info'),
    ]);

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
    const qHostSub = document.getElementById('scQdrantHostSub');
    const qPortSub = document.getElementById('scQdrantPortSub');
    const qCollectionSub = document.getElementById('scQdrantCollectionSub');
    const qTopKSub = document.getElementById('scQdrantTopKSub');
    const qDimSub = document.getElementById('scDimSub');
    if (qHostSub) qHostSub.textContent = `Host: ${st.qdrant_host || 'localhost'}`;
    if (qPortSub) qPortSub.textContent = `Port: ${st.qdrant_port || 6333}`;
    if (qCollectionSub) qCollectionSub.textContent = `Collection: ${st.qdrant_collection || 'memories'}`;
    if (qTopKSub) qTopKSub.textContent = `Top-K: ${st.qdrant_top_k || 5}`;
    if (qDimSub) qDimSub.textContent = `维度: ${st.embedding_dim || 1024}`;

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

    // Stats & chart
    await fetchAndDrawChart(_currentChartRange);

    // 记忆总数从数据库获取（启动时已同步 Qdrant）
    try {
      const countRes = await fetchJson(API + '/memory-count');
      const statTotal = document.getElementById('statTotal');
      if (statTotal) statTotal.textContent = countRes.count || 0;
    } catch (e) {
      console.error('[overview] failed to get memory count:', e);
    }

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
        name: '累计',
        type: 'line',
        data: chartData.map(d => d.total),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#7c3aed', width: 2 },
        itemStyle: { color: '#7c3aed' },
        areaStyle: { color: 'rgba(124,58,237,0.1)' },
      },
      {
        name: '新增',
        type: 'line',
        data: chartData.map(d => d.added || 0),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#22c55e', width: 2 },
        itemStyle: { color: '#22c55e' },
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
  try {
    const res = await fetchJson(API + '/chart-data?range=' + range);
    const data = res.data || [];

    // 更新今日新增统计
    const todayEl = document.getElementById('statToday');
    if (todayEl) {
      const isHourly = _currentChartRange === 'today';
      let todayAdded;
      if (isHourly) {
        todayAdded = data.reduce((sum, d) => sum + (d.added || 0), 0);
      } else {
        const todayStr = new Date().toISOString().slice(0, 10);
        todayAdded = (data.find(d => d.date === todayStr)?.added) || 0;
      }
      todayEl.textContent = todayAdded;
    }

    drawEChart(data, range);
  } catch(e) { console.error('[overview] chart error:', e); }
}
