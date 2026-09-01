import { useEffect, useState } from 'react'
import { fetchJson, postJson } from '../lib/api'
import './GateView.css'

const statusLabel: Record<string, string> = {
  stopped: '未连接',
  connecting: '连接中…',
  connected: '已连接',
  error: '连接异常',
}

const statusColor: Record<string, string> = {
  stopped: '#64748b',
  connecting: '#fbbf24',
  connected: '#86efac',
  error: '#fca5a5',
}

export default function GateView() {
  const [botId, setBotId] = useState('')
  const [secret, setSecret] = useState('')
  const [hasSecret, setHasSecret] = useState(false)
  const [status, setStatus] = useState('stopped')
  const [connected, setConnected] = useState(false)
  const [lastError, setLastError] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [statusType, setStatusType] = useState<'success' | 'error' | ''>('')

  function showMsg(msg: string, type: 'success' | 'error' = 'success') {
    setStatusMsg(msg)
    setStatusType(type)
    setTimeout(() => setStatusMsg(''), 4000)
  }

  async function loadConfig() {
    try {
      const r = await fetchJson<any>('/gate/config')
      setBotId(r.bot_id || '')
      setHasSecret(!!r.has_secret)
      setStatus(r.status || 'stopped')
      setConnected(!!r.connected)
      setLastError(r.last_error || '')
    } catch { /* ignore */ }
  }

  async function pollStatus() {
    try {
      const r = await fetchJson<any>('/gate/status')
      setStatus(r.status)
      setConnected(!!r.connected)
      if (r.last_error) setLastError(r.last_error)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    loadConfig()
    const t = setInterval(pollStatus, 3000)
    return () => clearInterval(t)
  }, [])

  async function saveConfig() {
    if (!botId.trim() || !secret.trim()) { showMsg('BotID 和 Secret 不能为空', 'error'); return }
    setLoading(true)
    try {
      const r = await postJson<any>('/gate/config', { bot_id: botId, secret })
      if (r.ok) { setHasSecret(true); showMsg('配置已保存') }
      else showMsg(r.message || '保存失败', 'error')
    } catch (e: any) {
      showMsg('保存失败: ' + (e.message || '未知错误'), 'error')
    } finally { setLoading(false) }
  }

  async function connect() {
    setLoading(true)
    try {
      const r = await postJson<any>('/gate/connect', {})
      if (r.ok) showMsg(r.message || '连接中…')
      else showMsg(r.message || '连接失败', 'error')
    } catch (e: any) {
      showMsg('连接失败: ' + (e.message || '未知错误'), 'error')
    } finally { setLoading(false) }
  }

  async function disconnect() {
    setLoading(true)
    try {
      const r = await postJson<any>('/gate/disconnect', {})
      showMsg(r.message || '已断开')
    } catch (e: any) {
      showMsg('断开失败: ' + (e.message || '未知错误'), 'error')
    } finally { setLoading(false) }
  }

  return (
    <div className="gate-page">
      <header className="page-header">
        <div className="title-wrap">
          <div className="page-title">Gate · 机器人接入</div>
          <div className="page-sub">配置企业微信智能机器人 WebSocket 长连接</div>
        </div>
      </header>

      {statusMsg && <div className={`status-bar ${statusType}`}>{statusMsg}</div>}

      <section className="card">
        <div className="card-row">
          <span className="card-label">连接状态</span>
          <span className="status-dot" style={{ background: statusColor[status] || '#64748b' }} />
          <span className="status-text" style={{ color: statusColor[status] || '#64748b' }}>
            {statusLabel[status] || status}
          </span>
          {lastError && status === 'error' && <span className="error-detail" title={lastError}>{lastError.slice(0, 60)}</span>}
        </div>
        <div className="card-row">
          <span className="card-label">当前机器人</span>
          <span className="card-value">{botId || '未配置'}</span>
        </div>
        <div className="card-actions">
          <button className="btn btn-primary" disabled={loading || connected || !botId || !hasSecret} onClick={connect}>
            {loading && status === 'connecting' ? '连接中…' : '启动连接'}
          </button>
          <button className="btn btn-danger" disabled={loading || !connected} onClick={disconnect}>断开连接</button>
        </div>
      </section>

      <section className="card">
        <div className="card-title">机器人凭证配置</div>
        <p className="card-desc">
          在企业微信管理后台 → 应用管理 → 智能机器人 创建机器人后，将 BotID 和 Secret 填入下方。
        </p>
        <div className="form-group">
          <label className="form-label">BotID</label>
          <input className="form-input" type="text" placeholder="请输入机器人 BotID" value={botId} onChange={(e) => setBotId(e.target.value)} disabled={connected} />
        </div>
        <div className="form-group">
          <label className="form-label">Secret</label>
          <div className="input-wrap">
            <input
              className="form-input"
              type={showSecret ? 'text' : 'password'}
              placeholder={hasSecret ? '已保存 Secret，留空则使用已有值' : '请输入 Secret'}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              disabled={connected}
            />
            <button className="btn-icon" onClick={() => setShowSecret((v) => !v)}>{showSecret ? '🙈' : '👁'}</button>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn btn-primary" disabled={loading || connected} onClick={saveConfig}>
            {loading ? '保存中…' : '保存配置'}
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-title">接入说明</div>
        <ol className="help-list">
          <li>登录 <a href="https://work.weixin.qq.com/wework_admin" target="_blank" rel="noopener">企业微信管理后台</a> → 应用管理 → 智能机器人</li>
          <li>创建机器人，接入方式选择 <strong>WebSocket 长连接</strong></li>
          <li>复制 BotID 和 Secret 填入上方配置框并保存</li>
          <li>点击「启动连接」建立长连接，状态变为「已连接」即成功</li>
          <li>用户在企业微信中向机器人发送消息，AiBrain 将自动回复</li>
        </ol>
      </section>
    </div>
  )
}
