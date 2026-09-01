import { useEffect, useState } from 'react'
import { fetchJson } from '../lib/api'
import './WikiView.css'

export default function WikiView() {
  const [files, setFiles] = useState<any[]>([])
  const [sideTab, setSideTab] = useState<'stats' | 'ops' | 'settings'>('stats')
  const [stats, setStats] = useState<any>(null)
  const [settings, setSettings] = useState<any>({})
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [sortKey, setSortKey] = useState('')
  const [sortAsc, setSortAsc] = useState(true)

  async function loadFiles() {
    try {
      const r = await fetchJson<any>('/wiki/list')
      setFiles(r.files || [])
    } catch { /* ignore */ }
  }

  async function loadStats() {
    try { setStats(await fetchJson<any>('/wiki/index')) } catch { /* ignore */ }
  }

  async function loadSettings() {
    try { setSettings(await fetchJson<any>('/wiki/settings')) } catch { /* ignore */ }
  }

  useEffect(() => {
    loadFiles()
    loadStats()
    loadSettings()
  }, [])

  async function search() {
    if (!searchQuery.trim()) return
    try {
      const r = await fetchJson<any>('/wiki/search', { method: 'POST', body: JSON.stringify({ query: searchQuery }) })
      setSearchResults(r.results || [])
    } catch { setSearchResults([]) }
  }

  function handleSort(key: string) {
    if (sortKey === key) setSortAsc((v) => !v)
    else { setSortKey(key); setSortAsc(true) }
  }

  const sortedFiles = [...files].sort((a, b) => {
    if (!sortKey) return 0
    const va = a[sortKey] ?? ''
    const vb = b[sortKey] ?? ''
    const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb))
    return sortAsc ? cmp : -cmp
  })

  return (
    <div className="wiki-page">
      <div className="wiki-header"><div className="page-title">Wiki 知识库</div></div>
      <div className="wiki-layout">
        <div className="wiki-main">
          <div className="wiki-search-bar">
            <input
              className="form-input"
              placeholder="搜索 Wiki..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') search() }}
            />
            <button className="btn-search" onClick={search}>搜索</button>
          </div>
          {searchResults.length > 0 && (
            <div className="wiki-search-results">
              <div className="wsr-header">搜索结果 ({searchResults.length}) <button onClick={() => setSearchResults([])}>✕</button></div>
              {searchResults.map((r: any, i: number) => (
                <div key={i} className="wsr-item">{r.text || r.content || JSON.stringify(r).slice(0, 200)}</div>
              ))}
            </div>
          )}
          <div className="wiki-files">
            <table className="wiki-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('name')}>文件名 {sortKey === 'name' && (sortAsc ? '↑' : '↓')}</th>
                  <th onClick={() => handleSort('size')}>大小 {sortKey === 'size' && (sortAsc ? '↑' : '↓')}</th>
                  <th onClick={() => handleSort('chunks')}>分块 {sortKey === 'chunks' && (sortAsc ? '↑' : '↓')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedFiles.length === 0 ? (
                  <tr><td colSpan={3} className="empty-state">暂无文件</td></tr>
                ) : (
                  sortedFiles.map((f: any, i: number) => (
                    <tr key={i}>
                      <td>{f.name || f.file || '--'}</td>
                      <td>{f.size ?? '--'}</td>
                      <td>{f.chunks ?? '--'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="wiki-side">
          <div className="wiki-side-tabs">
            <button className={`ws-tab${sideTab === 'stats' ? ' active' : ''}`} onClick={() => setSideTab('stats')}>统计</button>
            <button className={`ws-tab${sideTab === 'ops' ? ' active' : ''}`} onClick={() => setSideTab('ops')}>操作</button>
            <button className={`ws-tab${sideTab === 'settings' ? ' active' : ''}`} onClick={() => setSideTab('settings')}>设置</button>
          </div>
          {sideTab === 'stats' && (
            <div className="ws-panel">
              <div className="setting-group"><span className="setting-label">文件数</span><span className="setting-desc">{stats?.total_files ?? '--'}</span></div>
              <div className="setting-group"><span className="setting-label">分块数</span><span className="setting-desc">{stats?.total_chunks ?? '--'}</span></div>
              <div className="setting-group"><span className="setting-label">索引状态</span><span className="setting-desc">{stats?.indexed ? '已索引' : '未索引'}</span></div>
            </div>
          )}
          {sideTab === 'ops' && (
            <div className="ws-panel">
              <button className="btn-search" onClick={loadStats}>刷新统计</button>
              <button className="btn-search" onClick={loadFiles}>刷新文件</button>
            </div>
          )}
          {sideTab === 'settings' && (
            <div className="ws-panel">
              <div className="setting-group">
                <span className="setting-label">Wiki 目录</span>
                <input className="form-input" value={settings.wiki_dir ?? ''} onChange={(e) => setSettings((s: any) => ({ ...s, wiki_dir: e.target.value }))} />
              </div>
              <button className="btn-search">保存设置</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
