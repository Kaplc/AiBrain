import { useEffect, useRef, useState } from 'react'
import { fetchJson } from '../lib/api'
import './LogsView.css'

interface LogSource {
  key: string
  label: string
  icon: string
  defaultKeywords?: string
}

const LOG_SOURCES: LogSource[] = [
  { key: 'flask', label: '系统日志', icon: '📋', defaultKeywords: 'wiki,RAG,lightrag,index,search,embed,ERROR,WARNING,WARN,error,warning,warn,fail,failed,exception' },
  { key: 'mem0', label: 'Mem0 日志', icon: '🧠' },
  { key: 'embed', label: '语义模型', icon: '🔤' },
]

interface ParsedLine { raw: string; html: string; cls: string }

function escHtml(s: string): string {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function parseLine(line: string): ParsedLine {
  let cls = ''
  let html = escHtml(line)
  const m = line.match(/^\[([^\]]+)\]\s+\[(INFO|WARNING|ERROR|WARN)\]/i)
  if (m) {
    const lvl = m[2].toLowerCase()
    if (lvl.includes('error')) cls = 'log-level-error'
    else if (lvl.includes('warn')) cls = 'log-level-warn'
    else cls = 'log-level-info'
    html = `<span class="log-time">${escHtml(m[1])}</span> <span class="${cls}">[${m[2]}]</span>${escHtml(line.substring(m[0].length))}`
  } else if (/^\d{4}-\d{2}\/\d{2}\//.test(line)) {
    cls = 'log-level-info'
  } else if (/(?:error|fail|Exception)/i.test(line)) {
    cls = 'log-level-error'
  } else if (/warn|timeout|降级/i.test(line)) {
    cls = 'log-level-warn'
  }
  return { raw: line, html, cls }
}

export default function LogsView() {
  const [logLines, setLogLines] = useState<ParsedLine[]>([])
  const [meta, setMeta] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copyToast, setCopyToast] = useState(false)
  const [currentSource, setCurrentSource] = useState<LogSource>(LOG_SOURCES[0])
  const logWrapRef = useRef<HTMLDivElement | null>(null)

  async function loadLog(source?: LogSource) {
    const src = source || currentSource
    setLoading(true)
    setError('')
    setLogLines([])
    try {
      let url = `/logs/api?lines=300&type=${src.key}`
      if (src.defaultKeywords) url += `&keywords=${encodeURIComponent(src.defaultKeywords)}`
      const data = await fetchJson<any>(url, { retries: 5 })
      if (!data.lines) { setError(data.error || '暂无日志'); return }
      if (data.file) {
        setMeta(`${data.file} | 共 ${data.total_relevant || 0} 条，显示 ${data.returned} 条`)
      }
      setLogLines(data.lines.map((l: string) => parseLine(l)))
      setTimeout(() => {
        if (logWrapRef.current) logWrapRef.current.scrollTop = logWrapRef.current.scrollHeight
      }, 50)
    } catch (e: any) {
      setError('日志加载失败: ' + (e.message || e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadLog() }, [])

  async function copyLine(raw: string) {
    try { await navigator.clipboard.writeText(raw) } catch {
      const ta = document.createElement('textarea')
      ta.value = raw
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopyToast(true)
    setTimeout(() => setCopyToast(false), 1200)
  }

  function switchSource(src: LogSource) {
    if (src.key === currentSource.key) return
    setCurrentSource(src)
    loadLog(src)
  }

  return (
    <div className="logs-wrap">
      <div className="logs-title">日志</div>

      <div className="log-tabs">
        {LOG_SOURCES.map((src) => (
          <button
            key={src.key}
            className={`log-tab${currentSource.key === src.key ? ' active' : ''}`}
            onClick={() => switchSource(src)}
          >
            <span className="log-tab-icon">{src.icon}</span>
            {src.label}
          </button>
        ))}
      </div>

      <div className="log-section">
        <div className="log-header">
          <div className="log-title-text">{currentSource.label}</div>
          <span className="ft-meta">{meta}</span>
          <button className="btn-secondary" onClick={() => loadLog()}>刷新</button>
        </div>
        <div className="log-wrap" ref={logWrapRef}>
          {loading ? <div className="mini-loading" />
            : error ? <div className="empty-state">{error}</div>
            : logLines.length === 0 ? <div className="empty-state">点击「刷新」加载日志</div>
            : logLines.map((line, i) => (
              <div
                key={i}
                className={`log-line ${line.cls}`}
                title="点击复制"
                onClick={() => copyLine(line.raw)}
                dangerouslySetInnerHTML={{ __html: line.html }}
              />
            ))}
        </div>
      </div>
      {copyToast && <div className="copy-toast">已复制</div>}
    </div>
  )
}
