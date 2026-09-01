import { useEffect, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { fetchJson, postJson } from '../lib/api'
import { useToast } from '../lib/useToast'
import './StatsView.css'

export default function StatsView() {
  const [balance, setBalance] = useState<any>(null)
  const [balanceError, setBalanceError] = useState('')
  const [balanceLoading, setBalanceLoading] = useState(true)
  const [tokenData, setTokenData] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<'24h' | '7d' | '30d'>('24h')
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstRef = useRef<any>(null)
  const toast = useToast()

  async function pollBalance() {
    try {
      const d = await fetchJson<any>('/overview/balance')
      if (d.error) { setBalanceError(d.error); setBalanceLoading(false); return }
      setBalance(d)
      setBalanceError('')
      setBalanceLoading(false)
    } catch (e: any) {
      setBalanceError(e.message || '请求失败')
      setBalanceLoading(false)
    }
  }

  async function pollToken() {
    try {
      const data = await fetchJson<any>('/overview/token-usage')
      if (data.ok && data.periods) setTokenData(data.periods)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    pollBalance()
    pollToken()
    const t = setInterval(() => { pollBalance(); pollToken() }, 30000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!tokenData || !chartRef.current) return
    if (!chartInstRef.current) chartInstRef.current = echarts.init(chartRef.current)
    const chart = chartInstRef.current
    const period = tokenData[activeTab]
    if (!period?.data?.length) { chart.clear(); return }
    const dates = period.data.map((d: any) => d.date)
    chart.setOption({
      grid: { top: 8, right: 60, bottom: 28, left: 48 },
      tooltip: { trigger: 'axis', backgroundColor: '#1a1d27', borderColor: '#2d3149', textStyle: { color: '#e2e8f0', fontSize: 11 } },
      xAxis: {
        type: 'category', data: dates,
        axisLabel: { color: '#64748b', fontSize: 10, interval: 3 },
        axisLine: { lineStyle: { color: '#2d3149' } },
      },
      yAxis: { type: 'value', position: 'right', axisLabel: { color: '#64748b', fontSize: 10 }, splitLine: { lineStyle: { color: '#2d314933' } } },
      series: [
        { name: '消耗', type: 'line', smooth: true, data: period.data.map((d: any) => d.total_tokens), lineStyle: { width: 2 }, itemStyle: { color: '#a78bfa' }, symbol: 'none' },
        { name: '输入', type: 'line', smooth: true, data: period.data.map((d: any) => d.prompt_tokens), lineStyle: { width: 1.5 }, itemStyle: { color: '#60a5fa' }, symbol: 'none' },
        { name: '输出', type: 'line', smooth: true, data: period.data.map((d: any) => d.completion_tokens), lineStyle: { width: 1.5 }, itemStyle: { color: '#34d399' }, symbol: 'none' },
        { name: '缓存命中', type: 'line', smooth: true, data: period.data.map((d: any) => d.cache_hit_tokens), lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: '#fbbf24' }, symbol: 'none' },
      ],
    })
  }, [tokenData, activeTab])

  const fmt = (v: string) => { const n = parseFloat(v); return isNaN(n) ? v : n.toFixed(2) }
  const info = balance?.balance_infos?.[0]
  const summary = tokenData?.[activeTab]?.summary || {
    prompt_tokens: 0, completion_tokens: 0, cache_hit_tokens: 0, total_tokens: 0, cache_hit_rate: 0,
  }

  return (
    <div className="stats-page">
      <div className="page-header"><div className="page-title">用量</div></div>
      <div className="stats-grid">
        {/* 余额卡片 */}
        <div className="stat-card">
          <div className="sc-header">
            <div className="sc-label">DeepSeek 余额</div>
            {balanceLoading ? <span className="badge badge-loading">加载中</span>
              : balanceError ? <span className="badge badge-err" title={balanceError}>不可用</span>
              : balance?.is_available ? <span className="badge badge-ok">可用</span>
              : <span className="badge badge-err">不可用</span>}
            <button className="btn-refresh" onClick={pollBalance} title="刷新">↻</button>
          </div>
          {balanceLoading ? <div className="balance-val">--</div>
            : balanceError ? (
              <>
                <div className="balance-val err">--</div>
                {balanceError.includes('API key') && <div className="sub-text">请在 LLM 设置中配置 API Key</div>}
              </>
            ) : (
              <>
                <div className="balance-val">¥ {fmt(info?.total_balance || '0')}</div>
                <div className="balance-detail">
                  <span>赠金: ¥{fmt(info?.granted_balance || '0')}</span>
                  <span>充值: ¥{fmt(info?.topped_up_balance || '0')}</span>
                </div>
                {balance?.today_cost && (
                  <div className="today-cost">
                    <span className="tc-label">今日消耗</span>
                    <span className="tc-value">¥{balance.today_cost.total_cost.toFixed(2)}</span>
                  </div>
                )}
              </>
            )}
        </div>

        {/* Token 用量卡片 */}
        <div className="stat-card token-card">
          <div className="sc-header">
            <div className="sc-label">LLM Token 用量</div>
            <div className="tab-group">
              {(['24h', '7d', '30d'] as const).map((t) => (
                <button key={t} className={`chart-tab${activeTab === t ? ' active' : ''}`} onClick={() => setActiveTab(t)}>{t}</button>
              ))}
            </div>
            <button className="btn-refresh" onClick={pollToken} title="刷新">↻</button>
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
        </div>
      </div>
    </div>
  )
}
