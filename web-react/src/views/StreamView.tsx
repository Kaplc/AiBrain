import { useEffect, useState } from 'react'
import { fetchJson, postJson } from '../lib/api'
import { useToast } from '../lib/useToast'
import './StreamView.css'

interface StreamItemData {
  id: number
  action: 'store' | 'search' | 'delete'
  content: string
  memory_id: string | null
  status: 'pending' | 'done' | 'error' | ''
  created_at: string
  entities?: string
}

interface StreamItem {
  data: StreamItemData
  isNew: boolean
}

function displayTime(item: StreamItemData): string {
  return (item.created_at || '').slice(11, 19)
}

function displayText(item: StreamItemData): string {
  return item.content || item.memory_id || ''
}

function statusIcon(status: string): string {
  if (status === 'pending') return '⏳'
  if (status === 'done') return '✓'
  if (status === 'error') return '✗'
  return ''
}

const actionMeta = {
  store: { label: '保存', dot: 'store', btn: 'store-btn' },
  search: { label: '查询', dot: 'search', btn: 'search-btn' },
  delete: { label: '删除', dot: 'delete', btn: 'delete-btn' },
}

function StreamColumn({ action, items, knownIds, children }: {
  action: 'store' | 'search' | 'delete'
  items: StreamItemData[]
  knownIds: Set<string>
  children: React.ReactNode
}) {
  const meta = actionMeta[action]
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  function toggleExpand(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="stream-column">
      <div className="stream-column-header">
        <div className={`stream-column-dot ${meta.dot}`} />
        <span>{meta.label}</span>
        <span className="stream-column-count">{items.length} 条</span>
      </div>
      {children}
      <div className="stream-list">
        {items.length === 0 ? (
          <div className="stream-empty">暂无{meta.label}记录</div>
        ) : (
          items.map((item) => {
            const expanded = expandedIds.has(item.id)
            const isNew = !knownIds.has(String(item.id))
            const text = displayText(item)
            return (
              <div
                key={item.id}
                className={`stream-item ${meta.dot}${isNew ? ' new' : ''}${expanded ? ' expanded' : ''}`}
                onClick={() => toggleExpand(item.id)}
              >
                <div className="si-top">
                  <span className={`si-status si-${item.status || 'done'}`}>{statusIcon(item.status)}</span>
                  <span className="si-time">{displayTime(item)}</span>
                </div>
                <div className={`si-text${expanded ? '' : ' clamp'}`}>{text}</div>
                {item.entities && (
                  <div className="si-entities">
                    {item.entities.split(',').filter(Boolean).map((e, i) => (
                      <span key={i} className="si-entity-tag">{e}</span>
                    ))}
                  </div>
                )}
                {item.memory_id && <div className="si-mid">{item.memory_id.slice(0, 16)}…</div>}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default function StreamView() {
  const [storeItems, setStoreItems] = useState<StreamItemData[]>([])
  const [searchItems, setSearchItems] = useState<StreamItemData[]>([])
  const [deleteItems, setDeleteItems] = useState<StreamItemData[]>([])
  const [knownIds, setKnownIds] = useState<Set<string>>(new Set())
  const [storeInput, setStoreInput] = useState('')
  const [storeLoading, setStoreLoading] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searchShowResults, setSearchShowResults] = useState(false)
  const [deleteInput, setDeleteInput] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const toast = useToast()

  async function loadStream() {
    try {
      const [storeRes, searchRes, deleteRes] = await Promise.all([
        fetchJson<any>('/stream/api?action=store&days=3'),
        fetchJson<any>('/stream/api?action=search&days=3'),
        fetchJson<any>('/stream/api?action=delete&days=3'),
      ])
      setStoreItems(storeRes.items || [])
      setSearchItems(searchRes.items || [])
      setDeleteItems(deleteRes.items || [])
      requestAnimationFrame(() => {
        const all = [...(storeRes.items || []), ...(searchRes.items || []), ...(deleteRes.items || [])]
        setKnownIds((prev) => {
          const next = new Set(prev)
          all.forEach((i) => next.add(String(i.id)))
          return next
        })
      })
    } catch (e) {
      console.error('[StreamView] load failed:', e)
    }
  }

  useEffect(() => {
    loadStream()
    const streamTimer = setInterval(loadStream, 2000)
    const statusTimer = setInterval(async () => {
      /* pending 状态轮询 */
      await loadStream()
    }, 1000)
    return () => { clearInterval(streamTimer); clearInterval(statusTimer) }
  }, [])

  async function storeMemory() {
    const text = storeInput.trim()
    if (!text) return
    setStoreLoading(true)
    try {
      await postJson('/memory/store', { text })
      setStoreInput('')
      toast.show('记忆已保存')
      setTimeout(loadStream, 600)
    } catch (e: any) {
      toast.show('保存失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      setStoreLoading(false)
    }
  }

  async function searchMemory() {
    const query = searchInput.trim()
    if (!query) return
    setSearchLoading(true)
    setSearchResults([])
    setSearchShowResults(true)
    try {
      const res = await postJson<{ results: any[] }>('/memory/search', { query })
      setSearchResults(res.results || [])
    } catch (e: any) {
      toast.show('搜索失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      setSearchLoading(false)
    }
  }

  async function deleteMemory() {
    const id = deleteInput.trim()
    if (!id) return
    setDeleteLoading(true)
    try {
      await postJson('/memory/delete', { memory_id: id })
      setDeleteInput('')
      toast.show('记忆已删除')
      setTimeout(loadStream, 600)
    } catch (e: any) {
      toast.show('删除失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      setDeleteLoading(false)
    }
  }

  const totalCount = `MCP ${storeItems.length} 条 / 搜索 ${searchItems.length} 条 / 删除 ${deleteItems.length} 条`

  return (
    <div className="stream-wrap">
      <div className="stream-header">
        <div className="stream-title">记忆流</div>
        <div className="stream-count">{totalCount}</div>
      </div>

      <div className="stream-columns">
        {/* 保存列 */}
        <StreamColumn action="store" items={storeItems} knownIds={knownIds}>
          <div className="stream-action-form">
            <textarea
              className="stream-action-textarea"
              placeholder="输入要保存的记忆文本..."
              rows={2}
              value={storeInput}
              onChange={(e) => setStoreInput(e.target.value)}
              onKeyDown={(e) => { if (e.ctrlKey && e.key === 'Enter') storeMemory() }}
            />
            <button className="stream-action-btn store-btn" disabled={storeLoading || !storeInput.trim()} onClick={storeMemory}>
              {storeLoading ? <span className="action-spinner" /> : '保存'}
            </button>
          </div>
        </StreamColumn>

        {/* 查询列 */}
        <StreamColumn action="search" items={searchItems} knownIds={knownIds}>
          <div className="stream-action-form">
            <input
              className="stream-action-input"
              placeholder="搜索长时记忆..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') searchMemory() }}
            />
            <button className="stream-action-btn search-btn" disabled={searchLoading || !searchInput.trim()} onClick={searchMemory}>
              {searchLoading ? <span className="action-spinner" /> : '搜索'}
            </button>
          </div>
          {searchShowResults && (
            <div className="search-results-wrap">
              <div className="search-results-header">
                <span className="search-results-title">搜索结果 ({searchResults.length})</span>
                <button className="search-results-close" onClick={() => { setSearchShowResults(false); setSearchResults([]) }}>✕</button>
              </div>
              {searchResults.length === 0 ? (
                <div className="search-empty">无结果</div>
              ) : (
                searchResults.map((r: any, idx: number) => (
                  <div key={r.memory_id || idx} className="search-result-item">
                    <div className="search-result-text">{r.text || r.content}</div>
                    <div className="search-result-bottom">
                      <span className="search-result-id">{(r.id || r.memory_id || '')?.slice(0, 16)}…</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </StreamColumn>

        {/* 删除列 */}
        <StreamColumn action="delete" items={deleteItems} knownIds={knownIds}>
          <div className="stream-action-form">
            <input
              className="stream-action-input"
              placeholder="输入 memory_id 删除..."
              value={deleteInput}
              onChange={(e) => setDeleteInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') deleteMemory() }}
            />
            <button className="stream-action-btn delete-btn" disabled={deleteLoading || !deleteInput.trim()} onClick={deleteMemory}>
              {deleteLoading ? <span className="action-spinner" /> : '删除'}
            </button>
          </div>
        </StreamColumn>
      </div>
    </div>
  )
}
