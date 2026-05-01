/* 总览页面 */
var _sysInfoTimer   = null;
var _modelTimer     = null;   // 模型 card 轮询
var _qdrantTimer    = null;   // Qdrant card 轮询（共用 /status 响应）
var _flaskTimer     = null;   // Flask card 轮询（重启期间等待恢复）
var _currentChartRange = 'today';
var _currentDataView   = 'cumulative';
var _resizeTimer    = null;

// ── 模型 card 轮询 ───────────────────────────────────────────
// 每秒查 /status，model_loaded && qdrant_ready 后自动停止
function startModelPoll() {
  if (_modelTimer) clearInterval(_modelTimer);
  // 只有未 OK 时才置 loading（不重复写 DOM）
  var mb = document.getElementById('scModelBadge');
  var ms = document.getElementById('scModelSub');
  if (mb && mb.textContent !== 'OK' && !mb.querySelector('.mini-loading')) {
    mb.innerHTML = '<span class="mini-loading sm"></span>'; mb.className = 'sc-badge';
  }
  if (ms && !ms.textContent.trim()) ms.textContent = '加载中...';

  _modelTimer = setInterval(async () => {
    if (!document.getElementById('scModelBadge')) { clearInterval(_modelTimer); _modelTimer = null; return; }
    try {
      var st = await fetch(API + '/status').then(r => r.json());
      _updateModelCard(st);
      _updateQdrantBadge(st);   // 顺带更新 Qdrant badge（同一个请求）
      if (st.model_loaded && st.qdrant_ready) { clearInterval(_modelTimer); _modelTimer = null; }
    } catch {}
  }, 2000);
}

// ── Flask card 轮询 ──────────────────────────────────────────
// waitRestart=true：等 Flask 从死到活（请求失败时显示倒计时）
// waitRestart=false：直接刷新一次 Flask card
function startFlaskPoll(waitRestart, onBack) {
  if (_flaskTimer) clearInterval(_flaskTimer);
  var waited = 0;
  var hasFailed = false;   // 必须先经历失败（旧进程死掉），再成功才算真正恢复
  _flaskTimer = setInterval(async () => {
    waited += 1000;
    if (!document.getElementById('scFlaskBadge')) { clearInterval(_flaskTimer); _flaskTimer = null; return; }
    try {
      var st = await fetch(API + '/status').then(r => r.json());
      if (!st.flask_pid) return;
      if (waitRestart && !hasFailed) return;   // 旧进程还在，不算恢复
      // Flask 已恢复
      clearInterval(_flaskTimer); _flaskTimer = null;
      var cb = onBack;
      onBack = null;
      _updateFlaskCard(st);
      var fb = document.getElementById('scFlaskBadge');
      if (fb) { fb.textContent = 'OK'; fb.className = 'sc-badge green'; }
      if (cb) cb(st);
    } catch {
      hasFailed = true;   // 标记已经历过失败（旧进程已死）
      if (waitRestart) {
        var fb = document.getElementById('scFlaskBadge');
        if (fb) fb.textContent = '重启' + Math.floor(waited / 1000) + 's';
      }
      if (waited > 30000) {
        clearInterval(_flaskTimer); _flaskTimer = null;
        var fb2 = document.getElementById('scFlaskBadge');
        if (fb2) { fb2.textContent = 'ERR'; fb2.className = 'sc-badge red'; }
      }
    }
  }, 1000);
}

// ── Qdrant card 轮询 ─────────────────────────────────────────
// 每秒查 /status，qdrant_ready 后自动停止
function startQdrantPoll() {
  if (_qdrantTimer) clearInterval(_qdrantTimer);
  // 只有未 OK 时才置 loading
  var qb = document.getElementById('scQdrantBadge');
  if (qb && qb.textContent !== 'OK' && !qb.querySelector('.mini-loading')) {
    qb.innerHTML = '<span class="mini-loading sm"></span>'; qb.className = 'sc-badge';
  }

  _qdrantTimer = setInterval(async () => {
    if (!document.getElementById('scQdrantBadge')) { clearInterval(_qdrantTimer); _qdrantTimer = null; return; }
    try {
      var st = await fetch(API + '/status').then(r => r.json());
      _updateQdrantCard(st);
      if (st.qdrant_ready) { clearInterval(_qdrantTimer); _qdrantTimer = null; }
    } catch {}
  }, 2000);
}

// ── card 更新函数 ────────────────────────────────────────────
function _updateModelCard(st) {
  var modelValue = document.getElementById('scModelValue');
  var modelSub   = document.getElementById('scModelSub');
  var modelBadge = document.getElementById('scModelBadge');
  if (st.model_loaded) {
    if (modelValue) modelValue.innerHTML = '';
    if (modelSub)   modelSub.innerHTML = `${st.embedding_model || 'bge-m3'} ${st.model_size || ''}`;
    // 状态变化时才写 DOM（避免重置动画）
    if (modelBadge && modelBadge.textContent !== 'OK') {
      modelBadge.textContent = 'OK'; modelBadge.className = 'sc-badge green';
    }
  } else {
    if (modelValue) modelValue.innerHTML = '';
    // 只有还没显示 spinner 时才写入（幂等）
    if (modelBadge && !modelBadge.querySelector('.mini-loading')) {
      modelBadge.innerHTML = '<span class="mini-loading sm"></span>';
      modelBadge.className = 'sc-badge';
    }
    if (modelSub && !modelSub.textContent.trim()) modelSub.textContent = '加载中...';
  }
}

function _updateQdrantCard(st) {
  var qBadge = document.getElementById('scQdrantBadge');
  if (qBadge) {
    if (st.qdrant_ready) {
      // 状态变化时才写
      if (qBadge.textContent !== 'OK') { qBadge.textContent = 'OK'; qBadge.className = 'sc-badge green'; }
    } else {
      // 只有还没显示 spinner 时才写入
      if (!qBadge.querySelector('.mini-loading')) {
        qBadge.innerHTML = '<span class="mini-loading sm"></span>'; qBadge.className = 'sc-badge';
      }
    }
  }
  var qHostPortSub   = document.getElementById('scQdrantHostPortSub');
  var qCollectionSub = document.getElementById('scQdrantCollectionSub');
  var qStorageSub    = document.getElementById('scQdrantStorageSub');
  var qTopKSub       = document.getElementById('scQdrantTopKSub');
  var qDimSub        = document.getElementById('scDimSub');
  var qDiskSizeSub   = document.getElementById('scQdrantDiskSizeSub');
  if (qHostPortSub)   qHostPortSub.textContent   = `${st.qdrant_host || 'localhost'}:${st.qdrant_port || 6333}`;
  if (qCollectionSub) qCollectionSub.textContent = `Collection: ${st.qdrant_collection || 'memories'}`;
  if (qStorageSub)    qStorageSub.textContent    = `存储: ${st.qdrant_storage_path || 'storage'}`;
  if (qTopKSub)       qTopKSub.textContent       = `Top-K: ${st.qdrant_top_k || 5}`;
  if (qDimSub)        qDimSub.textContent        = `维度: ${st.embedding_dim || 1024}`;
  if (qDiskSizeSub) {
    const diskSize = st.qdrant_disk_size || 0;
    let sizeStr = diskSize >= 1073741824 ? `${(diskSize/1073741824).toFixed(2)} GB`
                : diskSize >= 1048576    ? `${(diskSize/1048576).toFixed(1)} MB`
                : diskSize > 0           ? `${Math.round(diskSize/1024)} KB` : '-';
    qDiskSizeSub.textContent = `磁盘: ${sizeStr}`;
  }
}
function _updateQdrantBadge(st) { _updateQdrantCard(st); }  // 向后兼容

// 立即用当前 st 刷新所有 card（重启后主动更新用）
function _refreshAllCards(st) {
  if (!st) return;
  _updateFlaskCard(st);
  var fb = document.getElementById('scFlaskBadge');
  if (fb) { fb.textContent = st.flask_pid ? 'OK' : 'ERR'; fb.className = 'sc-badge ' + (st.flask_pid ? 'green' : 'red'); }
  _updateQdrantBadge(st);
  _updateModelCard(st);
}


function onPageLoad() {
  console.log('[overview] onPageLoad start');
  // 立即加载图表和记忆总数（不等待模型）
  console.log('[overview] fetching chart and memory count');
  fetchAndDrawChart(_currentChartRange);
  fetchMemoryCount();

  // 加载页面数据
  console.log('[overview] loading overview page data');
  loadOverviewPage();

  // 模型 & Qdrant 状态轮询
  startModelPoll();
  startQdrantPoll();

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
      if (_currentDataView === 'added') {
        await fetchAddedChart();
      } else {
        await fetchAndDrawChart(range);
      }
    });
  }
  // 数据视图 tab 切换（累计曲线 / 新增曲线）
  var dataTabsEl = document.getElementById('dataTabs');
  if (dataTabsEl) {
    dataTabsEl.addEventListener('click', function(e) {
      var btn = e.target.closest('.data-tab');
      if (!btn) return;
      var view = btn.dataset.view;
      if (!view) return;
      _currentDataView = view;
      dataTabsEl.querySelectorAll('.data-tab').forEach(function(t) { t.classList.remove('active'); });
      btn.classList.add('active');
      var chartView = document.getElementById('chartView');
      var addedView = document.getElementById('addedView');
      var chartHeaderRight = document.getElementById('chartHeaderRight');
      var chartLegend = document.getElementById('chartLegend');
      if (view === 'cumulative') {
        if (chartView) chartView.style.display = '';
        if (addedView) addedView.style.display = 'none';
        if (chartHeaderRight) chartHeaderRight.style.display = '';
      } else {
        if (chartView) chartView.style.display = 'none';
        if (addedView) addedView.style.display = '';
        if (chartHeaderRight) chartHeaderRight.style.display = '';
        // 切换legend只显示新增
        if (chartLegend) chartLegend.innerHTML = '<span><i class="ldot green"></i>新增</span>';
        fetchAddedChart();
      }
      // 累计曲线时legend只显示累计
      if (view === 'cumulative' && chartLegend) {
        chartLegend.innerHTML = '<span><i class="ldot purple"></i>累计</span>';
      }
    });
  }
  console.log('[overview] onPageLoad done');
}

function cleanup() {
  if (_modelTimer)  { clearInterval(_modelTimer);  _modelTimer  = null; }
  if (_qdrantTimer) { clearInterval(_qdrantTimer); _qdrantTimer = null; }
  if (_flaskTimer)  { clearInterval(_flaskTimer);  _flaskTimer  = null; }
  if (_sysInfoTimer) { clearInterval(_sysInfoTimer); _sysInfoTimer = null; }
  if (_resizeTimer) { clearTimeout(_resizeTimer); _resizeTimer = null; }
  if (_chartInstance && _chartInstance.getDom()) { _chartInstance.dispose(); _chartInstance = null; }
  if (_addedChartInstance && _addedChartInstance.getDom()) { _addedChartInstance.dispose(); _addedChartInstance = null; }
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

function _formatUptime(seconds) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function _updateFlaskCard(st) {
  if (!st) return;
  const sub1 = document.getElementById('scFlaskSub1');
  const sub2 = document.getElementById('scFlaskSub2');
  const sub3 = document.getElementById('scFlaskSub3');
  const sub4 = document.getElementById('scFlaskSub4');
  if (sub1) sub1.textContent = `端口: ${st.flask_port || '?'}`;
  if (sub2) sub2.textContent = `PID: ${st.flask_pid || '?'}`;
  if (sub3) sub3.textContent = `运行: ${_formatUptime(st.flask_uptime || 0)}`;
  if (sub4) sub4.textContent = `热重载: ${st.flask_reload ? 'ON' : 'OFF'}`;
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

    // Flask 状态
    _updateFlaskCard(st);

    // Model & Qdrant — 由各自轮询负责持续更新，这里做一次初始渲染
    _updateModelCard(st);
    _updateQdrantCard(st);

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
  container.innerHTML = '';
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
        const rawData = _chartData ? _chartData[params[0].dataIndex] : null;
        const fullDate = rawData ? rawData.date : params[0].axisValue;
        return '<div style="font-weight:600;color:#a78bfa;margin-bottom:6px">' + fullDate + '</div>' +
          '<div style="display:flex;justify-content:space-between;gap:12px"><span style="color:#94a3b8">累计</span><span style="font-weight:600;color:#a78bfa">' + params[0].value + '</span></div>';
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
    if (_addedChartInstance) _addedChartInstance.resize();
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
    // 后端返回的 total 已经是正确的累计总数，直接使用

    // 更新时间段新增统计（计算范围内所有 added 之和）
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
        let rangeAdded = 0;
        data.forEach(function(d) { rangeAdded += d.added || 0; });
        statEl.textContent = rangeAdded;
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

/* ==================== 新增曲线图表 ==================== */
var _addedChartInstance = null;
var _addedChartData = null;

function initAddedChart() {
  var container = document.getElementById('addedChartContainer');
  if (!container) return;
  container.innerHTML = '';
  _addedChartInstance = echarts.init(container, null, { renderer: 'canvas' });
}

function drawAddedChart(data, range) {
  if (!_addedChartInstance) initAddedChart();
  if (!_addedChartInstance) return;
  _addedChartData = data;

  var dates = data.map(function(d) {
    if (range === 'today') return d.date;
    var day = d.date.slice(-2);
    if (day === '01') return d.date.slice(5, 7) + '月';
    return day;
  });

  var option = {
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
      minInterval: 1,
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
        var rawData = _addedChartData ? _addedChartData[params[0].dataIndex] : null;
        var fullDate = rawData ? rawData.date : params[0].axisValue;
        return '<div style="font-weight:600;color:#86efac;margin-bottom:6px">' + fullDate + '</div>' +
          '<div style="display:flex;justify-content:space-between;gap:12px"><span style="color:#94a3b8">新增</span><span style="font-weight:600;color:#86efac">' + params[0].value + '</span></div>';
      }
    },
    series: [
      {
        name: '新增',
        type: 'line',
        data: data.map(function(d) { return d.added || 0; }),
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: '#22c55e', width: 2 },
        itemStyle: { color: '#22c55e' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#22c55e33' },
              { offset: 1, color: '#22c55e05' }
            ]
          }
        },
      },
    ],
  };
  _addedChartInstance.setOption(option);
}

async function fetchAddedChart() {
  try {
    var res = await fetchJson(API + '/chart-data?range=' + _currentChartRange);
    if (!document.getElementById('addedChartContainer')) return;
    var data = res.data || [];

    // 更新增统计
    var total = 0;
    data.forEach(function(d) { total += d.added || 0; });
    var el = document.getElementById('addedStatToday');
    var lbl = document.getElementById('addedStatLabel');
    if (el) animateCount(el, total);
    if (lbl) {
      var labels = { 'today': '24h新增', 'week': '7天新增', 'month': '30天新增', 'all': '总新增' };
      lbl.textContent = labels[_currentChartRange] || '新增';
    }

    drawAddedChart(data, _currentChartRange);
  } catch (e) {
    console.error('[overview] added chart error:', e);
  }
}

/* ==================== Flask 重启 ==================== */
var _flaskRestarting = false;

async function restartFlask() {
  if (_flaskRestarting) return;
  var btn = document.getElementById('btnRestartFlask');
  var badge = document.getElementById('scFlaskBadge');
  if (!btn) return;

  // 二次确认
  if (!confirm('确认重启 Flask 后端？')) return;

  _flaskRestarting = true;
  btn.disabled = true;
  btn.textContent = '重启中...';
  if (badge) { badge.textContent = '...'; badge.className = 'sc-badge yellow'; }

  try {
    var resp = await fetch(API + '/flask/restart', { method: 'POST' });
    var data = await resp.json();
    if (data.ok) {
      btn.textContent = '已发送';
      // Flask card 轮询等恢复，恢复后刷新所有 card + 启动 model 轮询
      startFlaskPoll(true, function(st) {
        btn.disabled = false;
        btn.textContent = '重启';
        _flaskRestarting = false;
        _refreshAllCards(st);
        if (_chartInstance) { _chartInstance.dispose(); _chartInstance = null; }
        if (_addedChartInstance) { _addedChartInstance.dispose(); _addedChartInstance = null; }
        fetchAndDrawChart(_currentChartRange);
        fetchMemoryCount();
        // 启动模型 & Qdrant card 轮询（重启后需重新加载）
        startModelPoll();
        startQdrantPoll();
      });
    } else {
      _flaskRestarting = false;
      btn.disabled = false;
      btn.textContent = '重启';
      if (badge) { badge.textContent = 'ERR'; badge.className = 'sc-badge red'; }
      alert('重启失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    _flaskRestarting = false;
    btn.disabled = false;
    btn.textContent = '重启';
    if (badge) { badge.textContent = 'ERR'; badge.className = 'sc-badge red'; }
  }
}
