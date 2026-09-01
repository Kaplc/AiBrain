import { useEffect, useState } from 'react'
import { fetchJson, postJson } from '../lib/api'
import { useToast } from '../lib/useToast'
import { Memory, type MemoryRaw } from './types'

/* 搜索记忆面板 */
export function SearchPanel() {
  const [input, setInput] = useState('')
  const [results, setResults] = useState<Memory[]>([])
  const [activeQuery, setActiveQuery] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [loading, setLoading] = useState(false)
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())
  const toast = useToast()

  useEffect(() => {
    loadHistory()
    function onDocClick(e: MouseEvent) {
      const wrap = document.querySelector('.search-history-wrap')
      if (wrap && !wrap.contains(e.target as Node)) setShowHistory(false)
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  async function loadHistory() {
    try {
      const r = await fetchJson<{ history: { query: string }[] }>('/memory/search-history')
      setHistory((r.history || []).map((h) => h.query))
    } catch { /* ignore */ }
  }

  async function search(query?: string) {
    const q = (query ?? input).trim()
    if (!q || loading) return
    setLoading(true)
    setActiveQuery(q)
    setResults([])
    try {
      const r = await postJson<{ results: MemoryRaw[] }>('/memory/search', { query: q })
      setResults((r.results || []).map((raw) => new Memory(raw)))
      loadHistory()
    } catch {
      toast.show('搜索失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function clearHistory() {
    try {
      await fetch('/memory/search-history', { method: 'DELETE' })
      setHistory([])
    } catch { /* ignore */ }
  }

  async function del(id: string) {
    if (deletingIds.has(id)) return
    setDeletingIds((prev) => new Set(prev).add(id))
    try {
      const r = await postJson<{ result?: string; error?: string }>('/memory/delete', { memory_id: id })
      if (r.error) { toast.show(r.error, 'error'); return }
      toast.show(r.result || '删除成功')
      await new Promise((r) => setTimeout(r, 300))
      setResults((prev) => prev.filter((m) => m.id !== id))
    } catch {
      toast.show('删除失败', 'error')
    } finally {
      setDeletingIds((prev) => { const p = new Set(prev); p.delete(id); return p })
    }
  }

  return (
    <div className="tab-panel">
      <div className="search-bar">
        <div className="search-input-wrap">
          <input
            className="search-input"
            placeholder="输入关键词搜索记忆..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') search() }}
            disabled={loading}
          />
          <div className="search-history-wrap">
            <button className="btn-ghost" onClick={() => setShowHistory((v) => !v)} title="搜索历史">🕘</button>
            {showHistory && (
              <div className="history-dropdown">
                <div className="history-header">
                  <span>搜索历史</span>
                  <button className="btn-ghost" onClick={clearHistory}>清空</button>
                </div>
                {history.length === 0 ? (
                  <div className="history-empty">暂无历史</div>
                ) : (
                  history.map((q, i) => (
                    <div key={i} className="history-item" onClick={() => { setInput(q); setShowHistory(false); search(q) }}>
                      {q}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
          <button className="btn-accent" onClick={() => search()} disabled={loading || !input.trim()}>
            {loading ? '搜索中...' : '搜索'}
          </button>
        </div>
      </div>

      <div className="memory-list-container">
        {!activeQuery ? (
          <div className="empty"><div className="empty-icon">🔍</div><div className="empty-text">输入关键词开始搜索记忆</div></div>
        ) : results.length === 0 && !loading ? (
          <div className="empty"><div className="empty-icon">📭</div><div className="empty-text">没有找到相关记忆</div></div>
        ) : (
          <div className="result-list">
            {results.map((m) => (
              <div key={m.id} className={`memory-item${deletingIds.has(m.id) ? ' deleting' : ''}`}>
                <div className="mi-header">
                  {m.categoryLabel && <span className="mi-category">{m.categoryLabel}</span>}
                  <span className="mi-time">{m.formattedTime}</span>
                  {m.scorePercent && <span className="mi-score">{m.scorePercent}</span>}
                  <span className="mi-id" title={m.id}>{m.shortId}...</span>
                  <button className="btn-ghost btn-del" onClick={() => del(m.id)} title="删除">🗑</button>
                </div>
                <div className="mi-text">{m.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* 保存记忆面板 */
export function StorePanel() {
  const [input, setInput] = useState('')
  const [memories, setMemories] = useState<Memory[]>([])
  const toast = useToast()

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    try {
      const r = await postJson<{ memories: MemoryRaw[] }>('/memory/list', { source: 'user' })
      setMemories((r.memories || []).map((raw) => new Memory(raw)))
    } catch (e) {
      console.error('[memory] loadAll error:', e)
    }
  }

  async function save() {
    const text = input.trim()
    if (!text) return
    try {
      const r = await postJson<{ result?: string; error?: string }>('/memory/store', { text, memory_meta: { source: 'user' } })
      if (r.error) { toast.show(r.error, 'error'); return }
      toast.show(r.result || '保存成功')
      setInput('')
      loadAll()
    } catch {
      toast.show('连接失败', 'error')
    }
  }

  async function del(id: string) {
    try {
      const r = await postJson<{ result?: string; error?: string }>('/memory/delete', { memory_id: id })
      if (r.error) { toast.show(r.error, 'error'); return }
      toast.show(r.result || '删除成功')
      setMemories((prev) => prev.filter((m) => m.id !== id))
    } catch {
      toast.show('删除失败', 'error')
    }
  }

  return (
    <div className="tab-panel">
      <div className="store-form">
        <textarea
          className="store-textarea"
          placeholder="输入要保存的记忆内容..."
          rows={4}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.ctrlKey && e.key === 'Enter') save() }}
        />
        <button className="btn-accent" onClick={save} disabled={!input.trim()}>保存记忆</button>
      </div>
      <div className="memory-list-container">
        {memories.length === 0 ? (
          <div className="empty"><div className="empty-icon">📭</div><div className="empty-text">暂无已保存的记忆</div></div>
        ) : (
          <div className="result-list">
            {memories.map((m) => (
              <div key={m.id} className="memory-item">
                <div className="mi-header">
                  <span className="mi-time">{m.formattedTime}</span>
                  <span className="mi-id" title={m.id}>{m.shortId}...</span>
                  <button className="btn-ghost btn-del" onClick={() => del(m.id)} title="删除">🗑</button>
                </div>
                <div className="mi-text">{m.text}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* 合并（整理）记忆面板 - SSE 流式分析 */
interface OrganizeGroup {
  groupId: number
  similarity: number
  memories: Memory[]
  refinedText: string
  category: string
  isRefined: boolean
  isApplied: boolean
  isApplying: boolean
  isRefining: boolean
}

export function OrganizePanel() {
  const [groups, setGroups] = useState<OrganizeGroup[]>([])
  const [busy, setBusy] = useState(false)
  const [threshold, setThreshold] = useState('0.85')
  const toast = useToast()

  async function start() {
    if (busy) return
    setBusy(true)
    setGroups([])
    const sim = parseFloat(threshold) || 0.85
    const abort = new AbortController()
    try {
      const response = await fetch('/memory/organize/dedup/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ similarity_threshold: sim }),
        signal: abort.signal,
      })
      if (!response.ok) throw new Error('HTTP ' + response.status)
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let groupId = 0
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const msg = JSON.parse(line.slice(6))
            if (msg.type === 'batch' && msg.groups?.length) {
              const newItems = msg.groups.map((g: any) => ({
                groupId: groupId++,
                similarity: g.similarity,
                memories: (g.memories || []).map((raw: MemoryRaw) => new Memory(raw)),
                refinedText: '', category: 'reference', isRefined: false,
                isApplied: false, isApplying: false, isRefining: false,
              }))
              setGroups((prev) => [...prev, ...newItems])
            } else if (msg.type === 'done') {
              setBusy(false)
              if (!msg.groups?.length) toast.show('没有发现重复的记忆（共 ' + (msg.total || 0) + ' 条）')
              else toast.show('分析完成，共发现 ' + msg.groups.length + ' 组重复记忆')
            } else if (msg.type === 'error') {
              setBusy(false)
              toast.show('分析异常: ' + msg.error, 'error')
            }
          } catch { /* ignore */ }
        }
      }
      setBusy(false)
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        toast.show('流式分析连接失败', 'error')
        setBusy(false)
      }
    }
  }

  async function refineGroup(g: OrganizeGroup) {
    if (g.isRefining || g.isApplied) return
    setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, isRefining: true, isRefined: false, refinedText: '', category: 'reference' } : x))
    try {
      const r = await postJson<{ refined?: any[]; error?: string }>('/memory/organize/refine', {
        groups: [{
          group_id: g.groupId, similarity: g.similarity,
          memories: g.memories.map((m) => ({ id: m.id, text: m.text, timestamp: m.timestamp })),
        }],
      })
      if (r.error) throw new Error(r.error)
      const item = r.refined?.[0]
      if (item) {
        const originalText = g.memories.map((m, i) => `[${i + 1}] ${m.text}`).join('\n')
        setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? {
          ...x,
          refinedText: (!item.refined && !item.refined_text)
            ? [...g.memories].sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))[0]?.text || ''
            : (item.refined_text || originalText),
          category: item.category || 'reference',
          isRefined: true,
        } : x))
        toast.show(`组 ${g.groupId + 1} 合并完成`)
      }
    } catch (e: any) {
      toast.show(e.message || '合并失败', 'error')
    } finally {
      setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, isRefining: false } : x))
    }
  }

  async function applyGroup(g: OrganizeGroup) {
    if (g.isApplied || g.isApplying) return
    const newText = (g.refinedText || g.memories.map((m, i) => `[${i + 1}] ${m.text}`).join('\n')).trim()
    if (!newText) { toast.show('内容为空', 'error'); return }
    setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, isApplying: true } : x))
    try {
      const r = await postJson<{ error?: string }>('/memory/organize/apply', {
        items: [{ delete_ids: g.memories.map((m) => m.id), new_text: newText, category: g.category }],
      })
      if (r.error) { toast.show('写入失败: ' + r.error, 'error'); return }
      toast.show(`已合并该组记忆（删除 ${g.memories.length} 条，新增 1 条）`)
      setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, isApplied: true, isApplying: false } : x))
    } catch (e: any) {
      toast.show('写入失败: ' + e.message, 'error')
      setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, isApplying: false } : x))
    }
  }

  return (
    <div className="tab-panel">
      <div className="organize-toolbar">
        <select className="organize-select" value={threshold} onChange={(e) => setThreshold(e.target.value)}>
          <option value="0.95">相似度 ≥ 0.95（严格）</option>
          <option value="0.85">相似度 ≥ 0.85（推荐）</option>
          <option value="0.75">相似度 ≥ 0.75（宽松）</option>
        </select>
        <button className="btn-accent" onClick={start} disabled={busy}>{busy ? '分析中...' : '开始分析'}</button>
        {busy && <button className="btn-warn" onClick={() => { /* abort */ }}>暂停</button>}
      </div>
      <div className="memory-list-container">
        {groups.length === 0 && !busy ? (
          <div className="empty"><div className="empty-icon">🧹</div><div className="empty-text">点击「开始分析」查找重复记忆</div></div>
        ) : (
          <div className="organize-groups">
            {groups.map((g) => (
              <div key={g.groupId} className="organize-group-card">
                <div className="ogc-header">
                  <span className="ogc-title">组 {g.groupId + 1}</span>
                  <span className="ogc-similarity">相似度 {(g.similarity * 100).toFixed(1)}%</span>
                  <span className="ogc-count">{g.memories.length} 条</span>
                </div>
                <div className="ogc-memories">
                  {g.memories.map((m, i) => <div key={m.id} className="ogc-memory">[{i + 1}] {m.text}</div>)}
                </div>
                {g.isRefined && (
                  <textarea
                    className="ogc-refined"
                    value={g.refinedText}
                    onChange={(e) => setGroups((prev) => prev.map((x) => x.groupId === g.groupId ? { ...x, refinedText: e.target.value } : x))}
                    rows={3}
                  />
                )}
                <div className="ogc-actions">
                  {!g.isRefined ? (
                    <button className="btn-accent" onClick={() => refineGroup(g)} disabled={g.isRefining || g.isApplied}>
                      {g.isRefining ? '精炼中...' : 'AI 合并'}
                    </button>
                  ) : (
                    <button className="btn-accent" onClick={() => applyGroup(g)} disabled={g.isApplied || g.isApplying}>
                      {g.isApplying ? '写入中...' : g.isApplied ? '已合并' : '应用合并'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
