/* 日志视图模型 - 面向对象设计
 *
 * 作用：管理日志页面状态、日志解析、复制和滚动功能
 * 实现：提供单例 logsViewModel，支持多日志源 tab 切换，可配置注册新源
 *
 * 添加新的日志源：
 *   在 LOG_SOURCES 数组中新增一项即可，后端需支持对应 type 参数
 */

import { ref, nextTick } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

export interface LogData {
  lines: string[]
  file: string
  total_relevant: number
  returned: number
  error?: string
}

export interface ParsedLine {
  raw: string
  html: string
  cls: string
}

/** 日志源配置 */
export interface LogSource {
  key: string
  label: string
  icon?: string
  /** 默认关键词过滤（可选，空则显示所有行） */
  defaultKeywords?: string
}

/** 可注册的日志源列表 — 在此添加新的日志类型 */
const LOG_SOURCES: LogSource[] = [
  { key: 'flask', label: '系统日志', icon: '📋', defaultKeywords: 'wiki,RAG,lightrag,index,search,embed,ERROR,WARNING,WARN,error,warning,warn,fail,failed,exception' },
  { key: 'mem0', label: 'Mem0 日志', icon: '🧠' },
  { key: 'embed', label: '语义模型', icon: '🔤' },
]

export class LogsViewModel {
  // UI State
  readonly logLines = ref<ParsedLine[]>([])
  readonly meta = ref('')
  readonly loading = ref(false)
  readonly error = ref('')
  readonly copyToastVisible = ref(false)
  readonly logWrapEl = ref<HTMLElement | null>(null)

  // 日志源
  readonly sources = LOG_SOURCES
  readonly currentSource = ref<LogSource>(LOG_SOURCES[0])

  // Private
  private _api = useApi()
  private _toast = useToast()

  // ── 日志源切换 ─────────────────────────────────────────

  switchSource(source: LogSource): void {
    if (this.currentSource.value.key === source.key) return
    this.currentSource.value = source
    this.loadLog()
  }

  // ── 工具函数 ─────────────────────────────────────────────

  escHtml(s: string): string {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  parseLine(line: string): ParsedLine {
    let cls = ''
    let html = this.escHtml(line)

    const m = line.match(/^\[([^\]]+)\]\s+\[(INFO|WARNING|ERROR|WARN)\]/i)
    if (m) {
      const lvl = m[2].toLowerCase()
      if (lvl.indexOf('error') >= 0) cls = 'log-level-error'
      else if (lvl.indexOf('warn') >= 0) cls = 'log-level-warn'
      else cls = 'log-level-info'
      html =
        '<span class="log-time">' +
        this.escHtml(m[1]) +
        '</span> <span class="' +
        cls +
        '">[' +
        m[2] +
        ']</span>' +
        this.escHtml(line.substring(m[0].length))
    } else if (/^\d{4}-\d{2}\/\d{2}\//.test(line)) {
      cls = 'log-level-info'
    } else if (/(?:error|fail|Exception)/i.test(line)) {
      cls = 'log-level-error'
    } else if (/warn|timeout|降级/i.test(line)) {
      cls = 'log-level-warn'
    } else if (/\[(RAG|API)[→←⚠✗]\]/i.test(line)) {
      cls = 'log-level-info'
    }

    return { raw: line, html, cls }
  }

  // ── 加载日志 ─────────────────────────────────────────────

  async loadLog(): Promise<void> {
    const source = this.currentSource.value
    console.log('[logs] loadLog start, type=', source.key)
    this.loading.value = true
    this.error.value = ''
    this.logLines.value = []

    try {
      // 构造 URL
      let url = `/logs/api?lines=300&type=${source.key}`
      if (source.defaultKeywords) {
        url += `&keywords=${encodeURIComponent(source.defaultKeywords)}`
      }

      const data = await this._api.fetchJson<LogData>(url, 5)
      console.log('[logs] log data received:', data.lines ? data.lines.length + ' lines' : 'no lines')

      if (!data.lines) {
        this.error.value = data.error || '暂无日志'
        console.log('[logs] loadLog done, rendered empty')
        return
      }

      if (data.file) {
        this.meta.value =
          data.file +
          ' | 共 ' +
          (data.total_relevant || 0) +
          ' 条，显示 ' +
          data.returned +
          ' 条'
      }

      this.logLines.value = data.lines.map((l) => this.parseLine(l))
      nextTick(() => nextTick(() => this.scrollToBottom()))
      console.log('[logs] loadLog done, rendered content')
    } catch (e: any) {
      this.error.value = '日志加载失败: ' + (e.message || e)
      console.error('[log] loadLog error:', e)
    } finally {
      this.loading.value = false
    }
  }

  // ── 复制行 ──────────────────────────────────────────────

  async copyLine(raw: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(raw)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = raw
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    this.copyToastVisible.value = true
    setTimeout(() => {
      this.copyToastVisible.value = false
    }, 1200)
  }

  // ── 滚动 ────────────────────────────────────────────────

  scrollToBottom(): void {
    // scrollToBottom uses logWrapEl which is set via setLogWrap
  }

  setLogWrap(el: HTMLElement | null): void {
    this.logWrapEl.value = el
    console.log('[logs] setLogWrap:', el)
  }
}

// 单例
export const logsViewModel = new LogsViewModel()
