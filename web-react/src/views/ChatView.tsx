import { useEffect, useRef, useState, useCallback } from 'react'
import { useToast } from '../lib/useToast'
import './ChatView.css'

interface ChatMessage {
  id?: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  is_thought?: number
  isStreaming?: boolean
  created_at?: string
}

const API_BASE = window.location.origin

interface BrainState {
  life_loop_status: string
  current_activity: string
  current_focus: string
  idle_seconds: number
  energy: number
  mood: { label?: string; valence?: number; arousal?: number }
  open_loop_count: number
  pending_expression_count: number
  scheduler_running: boolean
  drives: Record<string, number>
  top_concerns: Array<{ node_id: string; effective: number }>
  reflection: {
    last_reflection_at: string | null
    last_reflection_summary: string
    beliefs: string[]
    interests: string[]
    goals: string[]
    open_questions: string[]
  }
  last_error: string
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function renderContent(msg: { role: string; content: string }): string {
  if (msg.role === 'user') return escapeHtml(msg.content)
  let html = escapeHtml(msg.content)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="lang-$1">$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/\n/g, '<br>')
  return html
}

function getDateSeparator(currentTime: string, prevTime: string | null): string {
  if (!currentTime) return ''
  const curDate = currentTime.slice(0, 10)
  if (!prevTime) return curDate
  return curDate !== prevTime.slice(0, 10) ? curDate : ''
}

function formatMsgTime(time: string): string {
  const m = time?.match(/\d{2}:\d{2}:\d{2}/)
  return m ? m[0] : ''
}

function timeAgo(ts: number | null): string {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  return `${Math.floor(diff / 3600)}小时前`
}

function fmtIdle(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h${m ? ` ${m}m` : ''}`
}

function formatDriveLabel(key: string): string {
  const map: Record<string, string> = { curiosity: '好奇', companionship: '陪伴', self_expression: '表达', completion: '完成' }
  return map[key] || key
}

export default function ChatView() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [currentStatus, setCurrentStatus] = useState('')
  const [inputText, setInputText] = useState('')
  const [loopState, setLoopState] = useState<any>({})
  const [showBrainDetail, setShowBrainDetail] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [systemPersona, setSystemPersona] = useState('')
  const [savingPersona, setSavingPersona] = useState(false)
  const [savedTip, setSavedTip] = useState(false)
  const [quotePreview, setQuotePreview] = useState('')
  const [quoteIndex, setQuoteIndex] = useState(-1)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [proactiveLoading, setProactiveLoading] = useState(false)

  const messagesRef = useRef<ChatMessage[]>([])
  const messagesEl = useRef<HTMLDivElement | null>(null)
  const lastSeqRef = useRef(0)
  const evtSourceRef = useRef<EventSource | null>(null)
  const typewriterTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pendingReloadRef = useRef(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const seqTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const toast = useToast()

  messagesRef.current = messages

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (messagesEl.current) {
        messagesEl.current.scrollTop = messagesEl.current.scrollHeight
      }
    })
  }, [])

  /* 打字机效果 */
  function typewriter(index: number, full: string) {
    if (!full) return
    setMessages((prev) => {
      const next = [...prev]
      if (next[index]) {
        next[index] = { ...next[index], content: '', isStreaming: true }
      }
      return next
    })
    const step = Math.max(1, Math.ceil(full.length / 50))
    let i = 0
    if (typewriterTimerRef.current) clearInterval(typewriterTimerRef.current)
    typewriterTimerRef.current = setInterval(() => {
      i += step
      const done = i >= full.length
      setMessages((prev) => {
        const next = [...prev]
        if (next[index]) {
          next[index] = { ...next[index], content: done ? full : full.slice(0, i), isStreaming: !done }
        }
        return next
      })
      if (done) {
        if (typewriterTimerRef.current) { clearInterval(typewriterTimerRef.current); typewriterTimerRef.current = null }
        if (pendingReloadRef.current) {
          pendingReloadRef.current = false
          loadMessagesSilent()
        }
      }
    }, 30)
  }

  async function loadMessages() {
    try {
      const resp = await fetch(`${API_BASE}/chat/history`)
      const data = await resp.json()
      if (data.messages) {
        setMessages(data.messages.map((m: any) => ({ role: m.role, content: m.content, created_at: m.created_at, isStreaming: false })))
        scrollToBottom()
      }
      try {
        const seqData = await (await fetch(`${API_BASE}/chat/seq`)).json()
        lastSeqRef.current = seqData.seq || 0
      } catch { /* ignore */ }
    } catch (e) {
      console.error('[chat] load messages failed:', e)
    }
  }

  async function loadMessagesSilent() {
    try {
      const resp = await fetch(`${API_BASE}/chat/history`)
      const data = await resp.json()
      if (!data.messages) return
      const cur = messagesRef.current
      const last = data.messages[data.messages.length - 1]
      const myLast = cur[cur.length - 1]
      if (data.messages.length === cur.length && last?.content === myLast?.content) return
      const prevLastAssistant = [...cur].reverse().find((m) => m.role === 'assistant')?.content
      const prevLen = cur.length
      setMessages(data.messages.map((m: any) => ({ role: m.role, content: m.content, created_at: m.created_at, isStreaming: false })))
      const newLen = data.messages.length
      const newLastAssistantIdx = newLen - 1
      const newLast = data.messages[newLastAssistantIdx]
      if (newLast?.role === 'assistant' && newLast.content && newLast.content !== prevLastAssistant) {
        typewriter(newLastAssistantIdx, newLast.content)
      } else if (newLen !== prevLen) {
        scrollToBottom()
      }
    } catch { /* 静默 */ }
  }

  async function loadState() {
    try {
      const resp = await fetch(`${API_BASE}/chat/state`)
      const data = await resp.json()
      setLoopState(data)
      if (data.current_status) setCurrentStatus(data.current_status)
    } catch { /* ignore */ }
  }

  async function checkSeq() {
    try {
      const data = await (await fetch(`${API_BASE}/chat/seq`)).json()
      if (data.seq > lastSeqRef.current) {
        lastSeqRef.current = data.seq
        reloadIfIdle()
      }
    } catch { /* 静默 */ }
  }

  async function reloadIfIdle() {
    const cur = messagesRef.current
    if (cur.length > 0 && cur[cur.length - 1].isStreaming) {
      pendingReloadRef.current = true
      return
    }
    await loadMessagesSilent()
  }

  function startEventStream() {
    if (evtSourceRef.current || typeof EventSource === 'undefined') return
    const es = new EventSource(`${API_BASE}/brain/events/stream`)
    es.addEventListener('brain_event', (ev: any) => {
      try {
        const payload = JSON.parse(ev.data)
        if (payload.source === 'workmemory' && payload.type === 'new_message') {
          reloadIfIdle()
        }
      } catch { /* 静默 */ }
    })
    es.onerror = () => { /* EventSource 自动重连 */ }
    evtSourceRef.current = es
  }

  function stopEventStream() {
    if (evtSourceRef.current) { evtSourceRef.current.close(); evtSourceRef.current = null }
  }

  useEffect(() => {
    loadMessages()
    loadState()
    pollTimerRef.current = setInterval(loadState, 10000)
    seqTimerRef.current = setInterval(checkSeq, 3000)
    checkSeq()
    startEventStream()
    async function loadWeworkStatus() {
      try { const r = await fetch('/gate/status'); await r.json() } catch { /* ignore */ }
    }
    loadWeworkStatus()
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
      if (seqTimerRef.current) clearInterval(seqTimerRef.current)
      if (typewriterTimerRef.current) clearInterval(typewriterTimerRef.current)
      stopEventStream()
    }
  }, [])

  async function sendMessage(text: string) {
    if (!text.trim() || sending) return
    const ts = new Date()
    const tsStr = `${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, '0')}-${String(ts.getDate()).padStart(2, '0')} ${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}:${String(ts.getSeconds()).padStart(2, '0')}`
    setMessages((prev) => [...prev, { role: 'user', content: text, created_at: tsStr }])
    scrollToBottom()
    setSending(true)
    try {
      const resp = await fetch(`${API_BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (resp.status === 503) {
        const data = await resp.json()
        toast.show(data.message || '请先配置 Chat', 'error')
        return
      }
      if (!resp.ok) {
        toast.show(`请求失败 ${resp.status}`, 'error')
        return
      }
    } catch (e: any) {
      toast.show(String(e), 'error')
    } finally {
      setSending(false)
    }
  }

  function handleSend() {
    let text = inputText.trim()
    if (!text || sending) return
    if (quotePreview) {
      text = `> ${quotePreview}\n\n${text}`
      setQuotePreview('')
      setQuoteIndex(-1)
    }
    setInputText('')
    sendMessage(text)
  }

  function handleKeydown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleClear() {
    try {
      await fetch(`${API_BASE}/chat/clear`, { method: 'POST' })
      setMessages([])
      toast.show('对话已清空', 'info')
    } catch {
      toast.show('清空失败', 'error')
    }
  }

  async function handleProactive() {
    if (proactiveLoading) return
    setProactiveLoading(true)
    try {
      await fetch(`${API_BASE}/chat/proactive`, { method: 'POST' })
      await loadMessagesSilent()
    } catch { /* ignore */ }
    setProactiveLoading(false)
  }

  async function openSettings() {
    setShowSettings(true)
    setSavedTip(false)
    try {
      const resp = await fetch('/settings/chat')
      const json = await resp.json()
      setSystemPersona(json.data?.system_persona || '')
    } catch { setSystemPersona('') }
  }

  async function saveSettings() {
    setSavingPersona(true)
    try {
      await fetch('/settings/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_persona: systemPersona }),
      })
      setSavedTip(true)
      setTimeout(() => setSavedTip(false), 2000)
    } catch { /* ignore */ }
    setSavingPersona(false)
  }

  function quoteMsg(text: string, index: number) {
    const lines = text.split('\n').filter(Boolean)
    let quote = lines.slice(0, 3).join('\n')
    if (lines.length > 3) quote += '\n...'
    setQuotePreview(quote)
    setQuoteIndex(index)
    setTimeout(() => {
      const ta = document.querySelector('.chat-input') as HTMLTextAreaElement
      ta?.focus()
    }, 50)
  }

  function jumpToQuote() {
    if (quoteIndex < 0 || !messagesEl.current) return
    const msgs = messagesEl.current.querySelectorAll('.message')
    const target = msgs[quoteIndex] as HTMLElement
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.style.transition = 'background 0.5s'
      target.style.background = 'rgba(124, 58, 237, 0.15)'
      setTimeout(() => { target.style.background = '' }, 1500)
    }
    setQuotePreview('')
    setQuoteIndex(-1)
  }

  async function copyMsgContent(text: string) {
    try { await navigator.clipboard.writeText(text) } catch {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    const flash = document.createElement('div')
    flash.className = 'copy-flash'
    flash.textContent = '已复制'
    document.body.appendChild(flash)
    setTimeout(() => flash.remove(), 1200)
  }

  function onScroll() {
    const el = messagesEl.current
    if (!el) return
    setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 100)
  }

  const brain = loopState.brain
  const stateLabel = (() => {
    if (loopState.is_busy) return { icon: '🟡', text: '思考中...', cls: 'busy' }
    if (loopState.idle_enabled) return { icon: '🟢', text: `已思考 ${loopState.idle_count} 次`, cls: 'idle' }
    return { icon: '⚪', text: '意识流已暂停', cls: 'paused' }
  })()

  const maxTokens = loopState.max_context_tokens || 400000
  const usedTokens = loopState.prompt_tokens || 0
  const tokenPercent = Math.min((usedTokens / maxTokens) * 100, 100)
  const hue = Math.round(120 - (tokenPercent / 100) * 120)
  const tokenColor = `hsl(${hue}, 80%, 45%)`

  return (
    <div className="chat-wrap">
      {/* 顶部状态条 */}
      <div className={`status-bar ${stateLabel.cls}`}>
        <span className="status-icon">{stateLabel.icon}</span>
        <span className="status-text">{stateLabel.text}</span>
        {loopState.idle_enabled && loopState.last_thought_at && (
          <span className="status-detail">上次 {timeAgo(loopState.last_thought_at)}</span>
        )}
        <button className="status-btn" onClick={openSettings} title="系统提示词">⚙</button>
        <button className="status-btn" onClick={handleClear} title="清空对话">🗑</button>
      </div>

      {/* 大脑循环状态条 */}
      {brain && (
        <div className={`brain-bar${brain.scheduler_running ? ' running' : ''}`} onClick={() => setShowBrainDetail((v) => !v)}>
          <span className="brain-bar-icon">{brain.scheduler_running ? '🧠' : '💤'}</span>
          <span className="brain-bar-activity">{brain.current_activity || 'wait'}{brain.current_focus ? ': ' + brain.current_focus.slice(0, 20) : ''}</span>
          <span className="brain-bar-idle">{fmtIdle(brain.idle_seconds || 0)}</span>
          {brain.pending_expression_count > 0 && <span className="brain-bar-pending">{brain.pending_expression_count} 待表达</span>}
          <span className="brain-bar-toggle">{showBrainDetail ? '▲' : '▼'}</span>
        </div>
      )}

      {/* 大脑详情面板 */}
      {showBrainDetail && brain && (
        <div className="brain-detail">
          <div className="bd-section">
            <div className="bd-title">🧬 驱动力</div>
            <div className="bd-drives">
              {Object.entries(brain.drives || {}).map(([key, val]: any) => (
                <div key={key} className="bd-drive">
                  <span className="bd-drive-label">{formatDriveLabel(key)}</span>
                  <div className="bd-drive-bar"><div className="bd-drive-fill" style={{ width: `${val * 100}%` }} /></div>
                  <span className="bd-drive-val">{(val * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
          {brain.top_concerns?.length > 0 && (
            <div className="bd-section">
              <div className="bd-title">🎯 当前关注</div>
              <div className="bd-concerns">
                {brain.top_concerns.map((c: any) => (
                  <span key={c.node_id} className="bd-concern" title={`effective: ${c.effective}`}>{c.node_id}</span>
                ))}
              </div>
            </div>
          )}
          <div className="bd-section bd-meta">
            <span className="bd-meta-item">能量 {(brain.energy * 100).toFixed(0)}%</span>
            <span className="bd-meta-item">心情 {brain.mood?.label || brain.mood?.valence?.toFixed(2) || '--'}</span>
            <span className="bd-meta-item">{brain.open_loop_count || 0} 闭环</span>
          </div>
          {(brain.reflection?.beliefs?.length > 0 || brain.reflection?.interests?.length > 0) && (
            <div className="bd-section">
              <div className="bd-title">💭 反思</div>
              <div className="bd-reflection">
                {brain.reflection.beliefs?.length > 0 && (
                  <div className="bd-rf-row"><span className="bd-rf-label">信念</span><span className="bd-rf-text">{brain.reflection.beliefs.join('; ')}</span></div>
                )}
                {brain.reflection.interests?.length > 0 && (
                  <div className="bd-rf-row"><span className="bd-rf-label">兴趣</span><span className="bd-rf-text">{brain.reflection.interests.join('; ')}</span></div>
                )}
                {brain.reflection.last_reflection_at && (
                  <div className="bd-rf-row dim"><span className="bd-rf-label">反思于</span><span className="bd-rf-text">{brain.reflection.last_reflection_at.slice(0, 19)}</span></div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 消息列表 */}
      <div className="messages" ref={messagesEl} onScroll={onScroll}>
        {messages.length === 0 && (
          <div className="empty-hint">
            <div className="empty-icon">💭</div>
            <div>开始与 AiBrain 对话</div>
            <div className="empty-sub">AI 会自动检索记忆库来理解上下文</div>
          </div>
        )}
        {messages.map((msg, i) => {
          const sep = getDateSeparator(msg.created_at || '', messages[i - 1]?.created_at || null)
          return (
            <div key={i}>
              {sep && <div className="date-separator">{sep}</div>}
              <div className={`message ${msg.role}${msg.is_thought === 1 ? ' thought' : ''}`}>
                {msg.is_thought === 1 && <span className="thought-badge">💭 思绪</span>}
                <div className="msg-content" dangerouslySetInnerHTML={{ __html: renderContent(msg) }} />
                {msg.isStreaming && (
                  <div className="stream-status">
                    <span className="stream-label">{currentStatus}</span>
                    <span className="cursor">▌</span>
                  </div>
                )}
                {msg.created_at && (
                  <div className={`msg-footer ${msg.role}`}>
                    <span className="msg-time">{formatMsgTime(msg.created_at)}</span>
                  </div>
                )}
              </div>
              {!msg.isStreaming && (
                <div className={`msg-actions ${msg.role}`}>
                  <button className="action-btn" onClick={() => copyMsgContent(msg.content)} title="复制">📋</button>
                  <button className="action-btn" onClick={() => quoteMsg(msg.content, i)} title="引用">💬</button>
                </div>
              )}
            </div>
          )
        })}
        {showScrollBtn && <button className="scroll-bottom-btn" onClick={scrollToBottom}>⬇</button>}
      </div>

      {/* 引用预览 */}
      {quotePreview && (
        <div className="quote-preview">
          <div className="quote-preview-bar" />
          <div className="quote-preview-text">{quotePreview}</div>
          <button className="quote-preview-close" onClick={jumpToQuote} title="跳转">↪</button>
          <button className="quote-preview-close" onClick={() => { setQuotePreview(''); setQuoteIndex(-1) }}>✕</button>
        </div>
      )}

      {/* 输入区 */}
      <div className="input-area">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          className="chat-input"
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          rows={1}
          onKeyDown={handleKeydown}
          disabled={sending}
        />
        <button className="send-btn" onClick={handleSend} disabled={sending || !inputText.trim()} title="发送">➤</button>
        <button className="proactive-btn" onClick={handleProactive} disabled={proactiveLoading} title="猫猫主动说一句">💬</button>
      </div>

      {/* Token 用量 */}
      <div className="token-bar">
        <div className="token-bar-track">
          <div className="token-bar-fill" style={{ width: `${tokenPercent}%`, background: tokenColor }} />
        </div>
        <span className="token-label">
          {(usedTokens / 1000).toFixed(1)}k / {(maxTokens / 1000).toFixed(1)}k ({tokenPercent.toFixed(1)}%)
        </span>
      </div>

      {/* 系统提示词设置弹窗 */}
      {showSettings && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowSettings(false) }}>
          <div className="modal-panel">
            <div className="modal-header">
              <div className="modal-title">系统提示词</div>
              <button className="modal-close" onClick={() => setShowSettings(false)}>✕</button>
            </div>
            <div className="modal-body">
              <textarea
                value={systemPersona}
                onChange={(e) => setSystemPersona(e.target.value)}
                className="modal-textarea"
                placeholder="输入系统提示词..."
                rows={8}
              />
            </div>
            <div className="modal-footer">
              {savedTip && <span className="save-tip">✓ 已保存</span>}
              <button className="btn-cancel" onClick={() => setShowSettings(false)}>取消</button>
              <button className="btn-save" onClick={saveSettings} disabled={savingPersona}>
                {savingPersona ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
