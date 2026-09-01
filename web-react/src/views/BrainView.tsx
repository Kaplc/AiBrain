import { useEffect, useState } from 'react'
import { fetchJson } from '../lib/api'
import './BrainView.css'

/* 简化格式化函数 */
function fmtSeconds(s: number | undefined | null): string {
  const v = Number(s)
  if (!Number.isFinite(v) || v < 0) return '--'
  const sec = Math.floor(v)
  if (sec < 60) return `${sec}s`
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${sec % 60}s`
}

function fmtPct(v: number | undefined | null): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  return `${Math.round(n * 100)}%`
}

function fmtTime(iso: any): string {
  if (!iso) return '--'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return '--'
    return d.toLocaleString()
  } catch { return '--' }
}

function truncate(s: any, n = 60): string {
  const t = s == null ? '' : String(s)
  return t.length > n ? t.slice(0, n) + '…' : t
}

export default function BrainView() {
  const [state, setState] = useState<any>(null)
  const [runs, setRuns] = useState<any[]>([])
  const [selectedRun, setSelectedRun] = useState<any>(null)
  const [refreshPaused, setRefreshPaused] = useState(false)
  const [lastRefreshedAt, setLastRefreshedAt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadState() {
    try {
      const data = await fetchJson<any>('/brain/state')
      setState(data)
      setError(data?.error || '')
    } catch (e: any) {
      setError(e?.message || '请求失败')
    }
  }

  async function loadRecent() {
    try {
      const data = await fetchJson<{ runs: any[] }>('/brain/runs/recent', { query: { limit: 20 } })
      setRuns(data?.runs ?? [])
    } catch {
      setRuns([])
    }
  }

  async function manualRefresh() {
    setLoading(true)
    await Promise.all([loadState(), loadRecent()])
    setLastRefreshedAt(new Date().toLocaleTimeString())
    setLoading(false)
  }

  useEffect(() => {
    manualRefresh()
  }, [])

  useEffect(() => {
    if (refreshPaused) return
    const t = setInterval(() => {
      loadState()
      loadRecent()
      setLastRefreshedAt(new Date().toLocaleTimeString())
    }, 4000)
    return () => clearInterval(t)
  }, [refreshPaused])

  async function selectRun(runId: string) {
    if (!runId) return
    try {
      const data = await fetchJson<any>(`/brain/runs/${encodeURIComponent(runId)}`)
      setSelectedRun(data?.error ? null : data)
    } catch {
      setSelectedRun(null)
    }
  }

  const life = state?.life_state

  return (
    <div className="brain-page" data-testid="brain-page">
      <header className="page-header">
        <div className="title-wrap">
          <div className="page-title">BrainLoop 观察台</div>
          <div className="page-sub">只读状态面板 · 实时观察后台数字生命循环</div>
        </div>
        <div className="refresh-controls">
          <span className="last-at">{lastRefreshedAt ? `更新于 ${lastRefreshedAt}` : ''}</span>
          <button
            className={`ctrl${!refreshPaused ? ' active' : ''}`}
            onClick={() => setRefreshPaused((v) => !v)}
            data-testid="brain-autorefresh-toggle"
          >
            {refreshPaused ? '⏸ 自动刷新已暂停' : '● 自动刷新中'}
          </button>
          <button className="ctrl primary" onClick={manualRefresh} disabled={loading} data-testid="brain-refresh-btn">
            {loading ? '刷新中…' : '↻ 立即刷新'}
          </button>
        </div>
      </header>

      {/* 状态概览 */}
      <div className="brain-status-panel">
        {error ? (
          <div className="bsp-error">⚠ {error}</div>
        ) : life ? (
          <div className="bsp-grid">
            <div className="bsp-item"><span className="bsp-label">循环状态</span><span className="bsp-value">{life.life_loop_status || '--'}</span></div>
            <div className="bsp-item"><span className="bsp-label">当前活动</span><span className="bsp-value">{life.current_activity || '--'}</span></div>
            <div className="bsp-item"><span className="bsp-label">当前关注</span><span className="bsp-value">{truncate(life.current_focus, 40) || '--'}</span></div>
            <div className="bsp-item"><span className="bsp-label">空闲时长</span><span className="bsp-value">{fmtSeconds(life.idle_seconds)}</span></div>
            <div className="bsp-item"><span className="bsp-label">能量</span><span className="bsp-value">{fmtPct(life.energy)}</span></div>
            <div className="bsp-item"><span className="bsp-label">心情</span><span className="bsp-value">{life.mood?.label || life.mood?.valence?.toFixed(2) || '--'}</span></div>
            <div className="bsp-item"><span className="bsp-label">自主等级</span><span className="bsp-value">{life.autonomy_level || '--'}</span></div>
            <div className="bsp-item"><span className="bsp-label">调度器</span><span className="bsp-value">{state?.scheduler_running ? '运行中' : '已停止'}</span></div>
            <div className="bsp-item"><span className="bsp-label">待表达</span><span className="bsp-value">{life.pending_expressions?.length ?? 0}</span></div>
          </div>
        ) : (
          <div className="bsp-loading">加载中...</div>
        )}
      </div>

      {/* run 列表 + 详情 */}
      <div className="run-row">
        <div className="brain-run-list">
          <div className="brl-header">
            <span>最近 Runs</span>
            <span className="brl-count">{runs.length}</span>
          </div>
          <div className="brl-items">
            {runs.length === 0 ? (
              <div className="empty-state">暂无 run 记录</div>
            ) : (
              runs.map((r) => (
                <div key={r.run_id} className="brl-item" onClick={() => selectRun(r.run_id)}>
                  <div className="brl-item-top">
                    <span className={`brl-mode ${r.mode}`}>{r.mode || 'unknown'}</span>
                    <span className="brl-activity">{r.selected_activity || '--'}</span>
                  </div>
                  <div className="brl-item-bottom">
                    <span>{fmtTime(r.started_at)}</span>
                    <span>{r.cycle_count ?? 0} cycles</span>
                    {r.last_error && <span className="brl-err">✗</span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        <div className="brain-run-detail">
          {selectedRun ? (
            <>
              <div className="brd-header">
                <span>Run 详情</span>
                <span className="brd-id">{selectedRun.run_id}</span>
              </div>
              <div className="brd-meta">
                <span>模式: {selectedRun.mode || '--'}</span>
                <span>活动: {selectedRun.selected_activity || '--'}</span>
                <span>停止原因: {selectedRun.stop_reason || '--'}</span>
              </div>
              <div className="brd-cycles">
                {(selectedRun.cycles || []).map((c: any, i: number) => (
                  <div key={i} className="brd-cycle">
                    <div className="brd-cycle-head">Cycle {c.cycle ?? c.cycle_index ?? i}</div>
                    {c.thought && <div className="brd-cycle-row"><span className="lbl">思考</span>{truncate(c.thought, 200)}</div>}
                    {c.tool_name && <div className="brd-cycle-row"><span className="lbl">工具</span>{c.tool_name}</div>}
                    {c.content && <div className="brd-cycle-row"><span className="lbl">输出</span>{truncate(c.content, 300)}</div>}
                    {c.error && <div className="brd-cycle-row err"><span className="lbl">错误</span>{truncate(c.error, 200)}</div>}
                  </div>
                ))}
                {(selectedRun.cycles || []).length === 0 && <div className="empty-state">无 cycle 数据</div>}
              </div>
            </>
          ) : (
            <div className="empty-state">点击左侧 run 查看详情</div>
          )}
        </div>
      </div>

      <footer className="page-foot">本面板为只读观察视图，不会触发 LLM、后台 tick、状态写入或主动发送。</footer>
    </div>
  )
}
