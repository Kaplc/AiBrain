import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchJson } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import './OverviewView.css'

/* 状态卡徽章组件 */
function Badge({ type }: { type: 'ok' | 'err' | 'loading' }) {
  return <span className={`badge badge-${type}`}>{type === 'ok' ? 'OK' : type === 'loading' ? '' : ''}</span>
}

/* ModelCard */
function ModelCard() {
  const [state, setState] = useState<{ badge: 'loading' | 'ok' | 'err'; sub: string; detail: string }>({
    badge: 'loading', sub: '加载中...', detail: '',
  })

  usePolling(async () => {
    try {
      const st = await fetchJson<any>('/overview/model')
      if (st.loaded) {
        setState({
          badge: 'ok', sub: '模型就绪',
          detail: st.embedding_model ? `${st.embedding_model} · ${st.embedding_dim}d` : '',
        })
      } else {
        setState({ badge: 'loading', sub: '加载中...', detail: '' })
      }
    } catch {
      setState({ badge: 'err', sub: '模型加载失败', detail: '' })
    }
  }, 2000)

  return (
    <div className="status-card">
      <div className="sc-header"><span className="sc-label">模型状态</span><Badge type={state.badge} /></div>
      <div className="sc-sub">{state.sub}</div>
      {state.detail && <div className="sc-detail">{state.detail}</div>}
    </div>
  )
}

/* QdrantCard */
function QdrantCard() {
  const [state, setState] = useState<{ badge: 'loading' | 'ok' | 'err'; detail: string }>({
    badge: 'loading', detail: '',
  })

  usePolling(async () => {
    try {
      const st = await fetchJson<any>('/overview/qdrant')
      if (st.ready) {
        const sizeGB = (st.disk_size / 1024 ** 3).toFixed(1)
        setState({ badge: 'ok', detail: `${st.host}:${st.port} · ${sizeGB}GB` })
      } else {
        setState({ badge: 'err', detail: '' })
      }
    } catch {
      setState({ badge: 'err', detail: '' })
    }
  }, 2000)

  return (
    <div className="status-card">
      <div className="sc-header"><span className="sc-label">Qdrant 状态</span><Badge type={state.badge} /></div>
      {state.detail && <div className="sc-sub">{state.detail}</div>}
    </div>
  )
}

/* FlaskCard（含重启 + 15s 倒计时） */
function FlaskCard() {
  const [badge, setBadge] = useState<'ok' | 'err' | 'restarting'>('ok')
  const [restarting, setRestarting] = useState(false)
  const [detail, setDetail] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  usePolling(async () => {
    try {
      const st = await fetchJson<any>('/overview/flask')
      setBadge('ok')
      setDetail(`PID: ${st.pid} · 端口: ${st.port}`)
    } catch { /* ignore */ }
  }, 2000)

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  async function restart() {
    if (restarting) return
    setRestarting(true)
    try {
      await fetchJson('/overview/flask/restart', { method: 'POST', body: '{}' })
      let sec = 0
      timerRef.current = setInterval(() => {
        sec++
        if (sec >= 15) {
          if (timerRef.current) clearInterval(timerRef.current)
          setRestarting(false)
        }
      }, 1000)
    } catch {
      setRestarting(false)
    }
  }

  const badgeType = badge === 'ok' ? (restarting ? 'loading' : 'ok') : 'err'
  return (
    <div className="status-card">
      <div className="sc-header">
        <span className="sc-label">Flask 状态</span>
        <Badge type={badgeType as any} />
        <button className="flask-restart-btn" onClick={restart} disabled={restarting}>
          {restarting ? '重启中...' : '重启'}
        </button>
      </div>
      {detail && <div className="sc-sub">{detail}</div>}
    </div>
  )
}

/* DeviceCard */
function DeviceCard() {
  const [info, setInfo] = useState<any>(null)
  usePolling(async () => {
    try {
      const st = await fetchJson<any>('/overview/system-info')
      setInfo((prev: any) => ({ ...prev, ...st }))
    } catch { /* ignore */ }
  }, 1000)

  return (
    <div className="status-card">
      <div className="sc-header"><span className="sc-label">设备信息</span></div>
      {info?.cpu_percent != null && <div className="sc-sub">CPU: {Number(info.cpu_percent).toFixed(1)}%</div>}
      {info?.memory_percent != null && <div className="sc-sub">内存: {Number(info.memory_percent).toFixed(1)}%</div>}
      {info?.gpu_name && <div className="sc-sub">GPU: {info.gpu_name}</div>}
    </div>
  )
}

/* TokenCard（ECharts 折线 + 统计） */
function TokenCard() {
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'24h' | '7d' | '30d'>('24h')
  const [periods, setPeriods] = useState<Record<string, any>>({})
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<any>(null)

  async function poll() {
    try {
      const data = await fetchJson<any>('/overview/token-usage')
      if (data.ok && data.periods) {
        setPeriods(data.periods)
        setLoading(false)
      }
    } catch { setLoading(false) }
  }

  usePolling(poll, 30000)
  useEffect(() => { poll() }, [])

  useEffect(() => {
    if (loading || !chartRef.current) return
    if (!chartInstRef.current) chartInstRef.current = echarts.init(chartRef.current)
    const chart = chartInstRef.current

    const period = periods[activeTab]
    if (!period?.data?.length) {
      chart.setOption({
        grid: { top: 8, right: 60, bottom: 28, left: 48 },
        xAxis: { type: 'category', data: [], axisLabel: { color: '#64748b', fontSize: 10 } },
        yAxis: { type: 'value', show: false },
        series: [],
      })
      return
    }
    const dates = period.data.map((d: any) => d.date)
    const totalData = period.data.map((d: any) => d.total_tokens)
    const promptData = period.data.map((d: any) => d.prompt_tokens)
    const completionData = period.data.map((d: any) => d.completion_tokens)
    const cacheData = period.data.map((d: any) => d.cache_hit_tokens)
    chart.setOption({
      grid: { top: 8, right: 60, bottom: 28, left: 48 },
      tooltip: { trigger: 'axis', backgroundColor: '#1a1d27', borderColor: '#2d3149', textStyle: { color: '#e2e8f0', fontSize: 11 } },
      legend: { show: false },
      xAxis: {
        type: 'category', data: dates,
        axisLabel: {
          color: '#64748b', fontSize: 10, interval: 3,
          formatter: (val: string) => {
            if (val.length <= 5) return val
            const t = val.slice(6)
            return t === '00:00' ? val.slice(0, 5) : t
          },
        },
        axisLine: { lineStyle: { color: '#2d3149' } },
      },
      yAxis: {
        type: 'value', position: 'right',
        axisLabel: { color: '#64748b', fontSize: 10 },
        splitLine: { lineStyle: { color: '#2d314933' } },
      },
      series: [
        { name: '消耗', type: 'line', smooth: true, data: totalData, lineStyle: { width: 2 }, itemStyle: { color: '#a78bfa' }, symbol: 'none' },
        { name: '输入', type: 'line', smooth: true, data: promptData, lineStyle: { width: 1.5 }, itemStyle: { color: '#60a5fa' }, symbol: 'none' },
        { name: '输出', type: 'line', smooth: true, data: completionData, lineStyle: { width: 1.5 }, itemStyle: { color: '#34d399' }, symbol: 'none' },
        { name: '缓存命中', type: 'line', smooth: true, data: cacheData, lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: '#fbbf24' }, symbol: 'none' },
      ],
    })
  }, [periods, activeTab, loading])

  const summary = periods[activeTab]?.summary || {
    prompt_tokens: 0, completion_tokens: 0, cache_hit_tokens: 0, total_tokens: 0, cache_hit_rate: 0,
  }

  return (
    <div className="status-card token-card-wide">
      <div className="sc-header">
        <span className="sc-label">LLM Token 用量</span>
        <div className="tab-group">
          {(['24h', '7d', '30d'] as const).map((t) => (
            <button key={t} className={`chart-tab${activeTab === t ? ' active' : ''}`} onClick={() => setActiveTab(t)}>{t}</button>
          ))}
        </div>
      </div>
      <div ref={chartRef} className="chart-box" />
      <div className="stat-row">
        <div className="sb"><div className="sb-v">{summary.total_tokens.toLocaleString()}</div><div className="sb-l">消耗</div></div>
        <div className="sb"><div className="sb-v blue">{summary.prompt_tokens.toLocaleString()}</div><div className="sb-l">输入</div></div>
        <div className="sb"><div className="sb-v green">{summary.completion_tokens.toLocaleString()}</div><div className="sb-l">输出</div></div>
        <div className="sb"><div className="sb-v yellow">{summary.cache_hit_tokens.toLocaleString()}</div><div className="sb-l">缓存命中</div></div>
      </div>
      <div className="cache-bar-wrap">
        <span className="cache-label">缓存命中率</span>
        <div className="cache-bar"><div className="cache-fill" style={{ width: `${(summary.cache_hit_rate || 0) * 100}%` }} /></div>
        <span className="cache-rate">{summary.cache_hit_rate > 0 ? `${(summary.cache_hit_rate * 100).toFixed(1)}%` : '--'}</span>
      </div>
      {loading && <div className="sc-sub">加载中...</div>}
    </div>
  )
}

/* BalanceCard */
function BalanceCard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<any>(null)

  async function poll() {
    try {
      const d = await fetchJson<any>('/overview/balance')
      if (d.error) { setError(d.error); setLoading(false); return }
      setData(d)
      setError('')
      setLoading(false)
    } catch (e: any) {
      setError(e.message || '请求失败')
      setLoading(false)
    }
  }

  usePolling(poll, 30000)
  useEffect(() => { poll() }, [])

  const info = data?.balance_infos?.[0]
  const fmt = (v: string) => {
    const n = parseFloat(v)
    return isNaN(n) ? v : n.toFixed(2)
  }

  return (
    <div className="status-card">
      <div className="sc-header">
        <span className="sc-label">DeepSeek 余额</span>
        {loading ? <span className="badge badge-loading">加载中</span>
          : error ? <span className="badge badge-err" title={error}>不可用</span>
          : data?.is_available ? <span className="badge badge-ok">可用</span>
          : <span className="badge badge-err">不可用</span>}
      </div>
      {loading ? <div className="balance-val">--</div>
        : error ? (
          <>
            <div className="balance-val err">--</div>
            {error.includes('API key') && <div className="sub-text">请在 LLM 设置中配置 API Key</div>}
          </>
        ) : (
          <>
            <div className="balance-val">¥ {fmt(info?.total_balance || '0')}</div>
            <div className="balance-detail">
              <span>赠金: ¥{fmt(info?.granted_balance || '0')}</span>
              <span>充值: ¥{fmt(info?.topped_up_balance || '0')}</span>
            </div>
            {data?.today_cost && (
              <div className="today-cost">
                <span className="tc-label">今日消耗</span>
                <span className="tc-value">¥{data.today_cost.total_cost.toFixed(2)}</span>
              </div>
            )}
          </>
        )}
    </div>
  )
}

export default function OverviewView() {
  return (
    <div className="overview-wrap">
      <div className="overview-row">
        <ModelCard />
        <QdrantCard />
        <FlaskCard />
        <DeviceCard />
      </div>
      <div className="overview-row">
        <TokenCard />
      </div>
      <div className="overview-row">
        <BalanceCard />
      </div>
    </div>
  )
}
