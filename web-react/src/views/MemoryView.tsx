import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import ForceGraphCtor from 'force-graph'
import { fetchJson, postJson } from '../lib/api'
import { useToast } from '../lib/useToast'
import { SearchPanel, StorePanel, OrganizePanel } from './MemoryPanels'
import './MemoryView.css'

type MemoryTab = 'search' | 'store' | 'organize' | 'settings' | 'graph' | 'entity' | 'chart'

/* 记忆数据图表 Tab（ECharts 累计/新增曲线） */
function ChartTab() {
  const [range, setRange] = useState<'today' | 'week' | 'month' | 'all'>('today')
  const [view, setView] = useState<'cumulative' | 'added'>('cumulative')
  const [statTotal, setStatTotal] = useState(0)
  const [statIncrement, setStatIncrement] = useState(0)
  const [incrementLabel, setIncrementLabel] = useState('24h新增')
  const [allTotal, setAllTotal] = useState(0)
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<any>(null)
  const toast = useToast()

  useEffect(() => {
    fetchJson<any>('/memory/count').then((r) => setStatTotal(r.count || 0)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstRef.current) chartInstRef.current = echarts.init(chartRef.current)
    const chart = chartInstRef.current

    async function draw() {
      try {
        const res = await fetchJson<any>(`/chart-data?range=${range}`)
        const data = res.data || []
        if (range !== 'all') {
          let rangeAdded = 0
          data.forEach((d: any) => { rangeAdded += d.added || 0 })
          setStatIncrement(rangeAdded)
          setIncrementLabel({ today: '24h新增', week: '7天新增', month: '30天新增' }[range] || '累计')
        } else {
          let total = 0
          data.forEach((d: any) => { total += d.added || 0 })
          setAllTotal(total)
        }

        const isAdded = view === 'added'
        const yData = isAdded ? data.map((d: any) => d.added || 0) : data.map((d: any) => d.total || 0)
        const color = isAdded ? '#22c55e' : '#7c3aed'
        const dates = data.map((d: any) => d.date || '')
        if (!data.length) { chart.clear(); return }
        const yMin = Math.round(Math.min(...yData))
        const yMax = Math.round(Math.max(...yData))
        const r = yMax - yMin
        const axisMin = yMin
        const axisMax = r === 0 ? yMax + 2 : yMax
        const step = r === 0 ? 1 : Math.max(1, Math.round(r / Math.min(r, 4)))
        const isHourly = (data[0]?.date || '').includes(':')
        const interval = isHourly ? (data.length > 12 ? 2 : 0) : Math.max(0, Math.floor(data.length / 8) - 1)
        chart.setOption({
          grid: { top: 8, right: 60, bottom: 36, left: 48 },
          xAxis: {
            type: 'category', data: dates, boundaryGap: false,
            axisLine: { lineStyle: { color: '#2d3149' } },
            axisLabel: { color: '#64748b', fontSize: 10, interval, formatter: (v: string) => (isHourly ? v : v.slice(5)) },
          },
          yAxis: {
            type: 'value', position: 'right', min: axisMin, max: axisMax, interval: step,
            axisLine: { show: false }, axisTick: { show: false },
            splitLine: { lineStyle: { color: '#1a1d27' } },
            axisLabel: { color: '#64748b', fontSize: 10, formatter: (v: number) => Math.round(v).toString() },
          },
          series: [{ type: 'line', smooth: true, data: yData, lineStyle: { color, width: 2 }, itemStyle: { color }, areaStyle: { color: color + '11' } }],
          tooltip: { trigger: 'axis', backgroundColor: '#1a1d27', borderColor: '#2d3149', textStyle: { color: '#e2e8f0', fontSize: 11 } },
        })
      } catch (e) { console.error('[chart] error:', e) }
    }
    draw()
  }, [range, view])

  /* 全部时间范围时隐藏增量统计 */
  const showIncrement = range !== 'all'

  return (
    <div className="tab-panel chart-tab-panel">
      <div className="chart-section">
        <div className="chart-tabs-row">
          <div className="chart-tabs">
            {(['cumulative', 'added'] as const).map((v) => (
              <button key={v} className={`data-tab${view === v ? ' active' : ''}`} onClick={() => setView(v)}>
                {v === 'cumulative' ? '累计曲线' : '新增曲线'}
              </button>
            ))}
          </div>
          <div className="chart-tabs">
            {(['today', 'week', 'month', 'all'] as const).map((r) => (
              <button key={r} className={`chart-tab${range === r ? ' active' : ''}`} onClick={() => setRange(r)}>
                {r === 'today' ? '近24小时' : r === 'week' ? '7天' : r === 'month' ? '30天' : '全部'}
              </button>
            ))}
          </div>
        </div>
        <div className="chart-title">记忆数据</div>
        <div ref={chartRef} className="chart-canvas" />
        <div className="chart-stats">
          <div className="stat-box">
            <div className="sb-label">记忆总数</div>
            <div className="sb-value">{statTotal.toLocaleString()}</div>
          </div>
          {showIncrement && (
            <div className="stat-box">
              <div className="sb-label">{incrementLabel}</div>
              <div className="sb-value">{statIncrement.toLocaleString()}</div>
            </div>
          )}
          {range === 'all' && view === 'added' && (
            <div className="stat-box">
              <div className="sb-label">总新增</div>
              <div className="sb-value">{allTotal.toLocaleString()}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* 图谱 Tab（force-graph 3D 视觉） */
function GraphTab() {
  const [loading, setLoading] = useState(false)
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
  const [showLabels, setShowLabels] = useState(true)
  const [showParticles, setShowParticles] = useState<boolean | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<any>(null)
  const toast = useToast()

  useEffect(() => {
    fetchJson<{ showGraphAnimation: boolean }>('/memory/settings')
      .then((r) => setShowParticles(r.showGraphAnimation))
      .catch(() => setShowParticles(true))
    loadGraph()
    return () => { if (graphRef.current) { graphRef.current._destructor(); graphRef.current = null } }
  }, [])

  useEffect(() => {
    if (showParticles === null || !containerRef.current || !graphData.nodes.length) return
    buildGraph()
  }, [graphData, showParticles])

  async function loadGraph() {
    setLoading(true)
    try {
      const data = await postJson<any>('/memory/graph/visualization', {})
      setGraphData(data)
    } catch (e: any) {
      toast.show('加载图谱失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  function hexToRgb(hex: string): [number, number, number] {
    const h = hex.replace('#', '')
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
    return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)]
  }

  function buildGraph() {
    if (!containerRef.current) return
    if (graphRef.current) { graphRef.current._destructor(); graphRef.current = null }
    const width = Math.max(containerRef.current.clientWidth, 300)
    const height = Math.max(containerRef.current.clientHeight, 400)

    const degree: Record<string, number> = {}
    for (const e of graphData.edges) {
      degree[e.source] = (degree[e.source] || 0) + 1
      degree[e.target] = (degree[e.target] || 0) + 1
    }
    const maxDeg = Math.max(1, ...Object.values(degree))
    const typeColors: Record<string, string> = { user: '#5B8FF9', self: '#F6BD16', rule: '#E86452', exp: '#6DC8EC' }
    const heatStops: Array<[number, number, number]> = [
      [100, 140, 255], [56, 211, 159], [251, 191, 36], [249, 115, 148],
    ]
    function lerpHeat(t: number): string {
      const n = heatStops.length - 1
      const fi = Math.min(t * n, n - 0.0001)
      const i = Math.floor(fi)
      const f = fi - i
      const a = heatStops[i], b = heatStops[i + 1]
      const r = Math.round(a[0] + (b[0] - a[0]) * f)
      const g = Math.round(a[1] + (b[1] - a[1]) * f)
      const bl = Math.round(a[2] + (b[2] - a[2]) * f)
      return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${bl.toString(16).padStart(2, '0')}`
    }

    const nodes = graphData.nodes.map((n: any) => {
      const color = typeColors[n.type] || lerpHeat((degree[n.id] || 0) / maxDeg)
      return { id: n.id, label: n.label, val: Math.max(1, n.memoryCount), color }
    })
    const links = graphData.edges.map((e: any) => ({ source: e.source, target: e.target }))

    const ForceGraph = (ForceGraphCtor as any).default ?? ForceGraphCtor
    const graph = ForceGraph()(containerRef.current)
      .graphData({ nodes, links })
      .width(width)
      .height(height)
      .backgroundColor('#020510')
      .nodeId('id')
      .nodeLabel('')
      .nodeVal('val')
      .nodeColor('color')
      .nodeRelSize(1)
      .linkColor(() => 'rgba(100,160,255,0.18)')
      .linkWidth(0.7)
      .linkDirectionalParticles(showParticles !== false ? 2 : 0)
      .linkDirectionalParticleWidth(1.8)
      .nodeCanvasObject((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        if (node.x == null || node.y == null) return
        const size = Math.sqrt(Math.max(1, node.val)) * 0.4 + 4
        const color = node.color || '#945FB9'
        const [nr, ng, nb] = hexToRgb(color)
        const rgb = `${nr},${ng},${nb}`
        const g1 = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, size * 5)
        g1.addColorStop(0, `rgba(${rgb},0.08)`)
        g1.addColorStop(1, 'transparent')
        ctx.beginPath(); ctx.arc(node.x, node.y, size * 5, 0, Math.PI * 2); ctx.fillStyle = g1; ctx.fill()
        const g2 = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, size * 2.5)
        g2.addColorStop(0, `rgba(${rgb},0.25)`)
        g2.addColorStop(1, 'transparent')
        ctx.beginPath(); ctx.arc(node.x, node.y, size * 2.5, 0, Math.PI * 2); ctx.fillStyle = g2; ctx.fill()
        ctx.beginPath(); ctx.arc(node.x, node.y, size * 1.45, 0, Math.PI * 2); ctx.fillStyle = `rgba(${rgb},0.35)`; ctx.fill()
        const g4 = ctx.createRadialGradient(node.x - size * 0.2, node.y - size * 0.2, 0, node.x, node.y, size)
        g4.addColorStop(0, `rgba(${Math.min(255, nr + 60)},${Math.min(255, ng + 60)},${Math.min(255, nb + 60)},1)`)
        g4.addColorStop(1, `rgba(${nr},${ng},${nb},1)`)
        ctx.beginPath(); ctx.arc(node.x, node.y, size, 0, Math.PI * 2); ctx.fillStyle = g4; ctx.fill()
        if (showLabels) {
          const label = String(node.label || node.id || '')
          const fontSize = Math.min(13, Math.max(7, 11 / globalScale))
          ctx.font = `${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          ctx.shadowColor = color
          ctx.shadowBlur = 6
          ctx.fillStyle = 'rgba(220,235,255,0.92)'
          ctx.fillText(label, node.x, node.y + size * 1.5 + 1)
          ctx.shadowBlur = 0
        }
      })
      .nodeCanvasObjectMode(() => 'replace')
      .enablePanInteraction(false)
      .d3AlphaDecay(0.008)
      .d3VelocityDecay(0.35)
      .warmupTicks(100)
      .cooldownTicks(200)
      .onEngineStop(() => { graphRef.current?.zoomToFit(600, 40) })
    graphRef.current = graph
  }

  async function handleAnimationToggle() {
    if (showParticles === null) return
    const newValue = !showParticles
    setShowParticles(newValue)
    if (graphRef.current) buildGraph()
    try { await postJson('/memory/settings', { showGraphAnimation: newValue }) } catch { /* 静默 */ }
  }

  return (
    <div className="graph-panel">
      <div className="graph-toolbar">
        <span className="graph-info">
          节点: {graphData.nodes.length} | 关系: {graphData.edges.length}
        </span>
        <div className="graph-toolbar-actions">
          <button className={`btn-toggle${showLabels ? ' active' : ''}`} onClick={() => setShowLabels((v) => !v)} title="Show/Hide Labels">标</button>
          <button className={`btn-toggle${showParticles ? ' active' : ''}`} onClick={handleAnimationToggle} title="Show/Hide Animation">动</button>
          <button className="btn-refresh" onClick={loadGraph} disabled={loading}>
            {loading ? '加载中...' : '刷新'}
          </button>
        </div>
      </div>
      {loading ? <div className="graph-loading">加载图谱数据...</div>
        : graphData.nodes.length === 0 ? <div className="graph-empty">暂无图谱数据</div>
        : <div ref={containerRef} className="graph-container" />}
    </div>
  )
}

/* 实体 Tab */
interface EntityStats {
  entity_nodes: number
  mentions: number
  memory_relations: number
  graph_loaded: boolean
  graph_nodes: number
  graph_edges: number
}

function EntityTab() {
  const [stats, setStats] = useState<EntityStats>({
    entity_nodes: 0, mentions: 0, memory_relations: 0,
    graph_loaded: false, graph_nodes: 0, graph_edges: 0,
  })
  const [rebuildState, setRebuildState] = useState<any>({ status: 'idle', progress_pct: 0, elapsed_seconds: 0 })
  const [logVisible, setLogVisible] = useState(false)
  const [logLines, setLogLines] = useState<string[]>([])
  const toast = useToast()

  useEffect(() => {
    loadStats()
    loadRebuildStatus()
  }, [])

  useEffect(() => {
    if (rebuildState.status !== 'running') return
    const t = setInterval(async () => {
      try {
        const d = await fetchJson<any>('/memory/graph/rebuild')
        setRebuildState(d)
        if (d.status === 'completed') toast.show('实体网络重建完成')
        else if (d.status === 'failed') toast.show('实体网络重建失败：' + (d.error || '未知错误'), 'error')
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(t)
  }, [rebuildState.status])

  async function loadStats() {
    try {
      const data = await fetchJson<EntityStats>('/memory/entity/stats')
      setStats((prev) => ({ ...prev, ...data }))
    } catch (e: any) {
      toast.show('加载实体统计失败: ' + e.message, 'error')
    }
  }

  async function loadRebuildStatus() {
    try { setRebuildState(await fetchJson<any>('/memory/graph/rebuild')) } catch { /* 静默 */ }
  }

  async function startRebuild() {
    try {
      await fetchJson('/memory/graph/rebuild', { method: 'POST', body: JSON.stringify({ workers: 5, batch_size: 10, delay: 1.0 }) })
      toast.show('已开始重建实体网络')
      await loadRebuildStatus()
    } catch (e: any) {
      toast.show('启动失败：' + (e?.message || '未知错误'), 'error')
    }
  }

  async function cancelRebuild() {
    try {
      await fetchJson('/memory/graph/rebuild/cancel', { method: 'POST', body: '{}' })
      toast.show('已发送取消指令')
    } catch (e: any) {
      toast.show('取消失败：' + (e?.message || '未知错误'), 'error')
    }
  }

  async function loadLog() {
    try {
      const data = await fetchJson<{ lines: string[] }>('/memory/graph/rebuild/log', { query: { lines: 100 } })
      setLogLines(data.lines ?? [])
    } catch { setLogLines([]) }
  }

  return (
    <div className="tab-panel entity-panel">
      <div className="entity-stats-row">
        <div className="entity-stat-card"><div className="esc-value">{stats.entity_nodes}</div><div className="esc-label">实体节点</div></div>
        <div className="entity-stat-card"><div className="esc-value">{stats.mentions}</div><div className="esc-label">实体提及</div></div>
        <div className="entity-stat-card"><div className="esc-value">{stats.memory_relations}</div><div className="esc-label">记忆关联</div></div>
        <div className="entity-stat-card">
          <div className="esc-value">{stats.graph_loaded ? `${stats.graph_nodes}/${stats.graph_edges}` : '--'}</div>
          <div className="esc-label">内存图 (节点/边)</div>
        </div>
        <button className="btn-ghost" onClick={loadStats} title="刷新">↻</button>
      </div>

      <div className="entity-rebuild-card">
        <div className="erc-header">
          <span className="erc-title">重建实体网络</span>
          {rebuildState.status === 'idle' && (
            <button className="btn-accent" onClick={startRebuild}>重建实体网络</button>
          )}
          {rebuildState.status === 'running' && (
            <button className="btn-warn" onClick={cancelRebuild}>取消</button>
          )}
          <button className="btn-ghost" onClick={() => { setLogVisible((v) => !v); if (!logVisible) loadLog() }}>
            查看日志
          </button>
        </div>
        {rebuildState.status === 'running' && (
          <div className="erc-progress">
            <div className="erc-progress-bar"><div className="erc-progress-fill" style={{ width: `${rebuildState.progress_pct || 0}%` }} /></div>
            <span>{rebuildState.processed}/{rebuildState.total} · {Math.round(rebuildState.progress_pct || 0)}%</span>
            <span className="erc-meta">线程 {rebuildState.workers} · LLM {rebuildState.llm_calls} 次 · 耗时 {rebuildState.elapsed_seconds}s</span>
          </div>
        )}
        {logVisible && (
          <div className="erc-log">
            {logLines.length === 0 ? '暂无日志' : logLines.map((l, i) => <div key={i} className="erc-log-line">{l}</div>)}
          </div>
        )}
      </div>
    </div>
  )
}

/* 记忆设置 Tab（功能固定启用，无配置项） */
function MemorySettingsPanel() {
  return (
    <div className="tab-panel">
      <div className="empty">
        <div className="empty-icon">⚙</div>
        <div className="empty-text">记忆功能全部固定启用（LLM 编码、情景节点、图增强搜索）</div>
      </div>
    </div>
  )
}

export default function MemoryView() {
  const [tab, setTab] = useState<MemoryTab>('search')
  const [count, setCount] = useState(0)

  useEffect(() => {
    fetchJson<{ count: number }>('/memory/count')
      .then((r) => setCount(r.count || 0))
      .catch(() => {})
  }, [])

  const tabs: Array<{ key: MemoryTab; label: string }> = [
    { key: 'search', label: '搜索记忆' },
    { key: 'store', label: '保存记忆' },
    { key: 'organize', label: '合并记忆' },
    { key: 'chart', label: '记忆数据' },
    { key: 'graph', label: '图谱' },
    { key: 'entity', label: '实体' },
    { key: 'settings', label: '⚙ 设置' },
  ]

  return (
    <div className="memory-layout">
      <nav className="memory-nav">
        <div className="nav-tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              className={`nav-tab${t.key === 'settings' ? ' nav-tab-settings' : ''}${tab === t.key ? ' active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="nav-stat">
          <span className="stat-value">{count}</span>
          <span className="stat-label">条记忆</span>
          <button
            className="btn-icon"
            onClick={() => fetchJson<{ count: number }>('/memory/count').then((r) => setCount(r.count || 0)).catch(() => {})}
            title="刷新"
          >↻</button>
        </div>
      </nav>

      {tab === 'search' && <SearchPanel />}
      {tab === 'store' && <StorePanel />}
      {tab === 'organize' && <OrganizePanel />}
      {tab === 'chart' && <ChartTab />}
      {tab === 'graph' && <GraphTab />}
      {tab === 'entity' && <EntityTab />}
      {tab === 'settings' && <MemorySettingsPanel />}
    </div>
  )
}
