/* 日志视图模型 - 面向对象设计 */

import { ref } from 'vue'
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

export class LogsViewModel {
  // UI State
  readonly logLines = ref<ParsedLine[]>([])
  readonly meta = ref('')
  readonly loading = ref(false)
  readonly error = ref('')
  readonly copyToastVisible = ref(false)
  readonly logWrapEl = ref<HTMLElement | null>(null)

  // Private
  private _api = useApi()
  private _toast = useToast()

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
    console.log('[logs] loadLog start')
    this.loading.value = true
    this.error.value = ''
    this.logLines.value = []

    try {
      const data = await this._api.fetchJson<LogData>('/wiki/log?lines=300', 5)
      console.log('[logs] log data received:', data.lines ? data.lines.length + ' lines' : 'no lines')

      if (!data.lines) {
        this.error.value = data.error || '无日志'
        console.log('[logs] loadLog done, rendered empty')
        return
      }

      if (data.file) {
        this.meta.value =
          data.file +
          ' | 共 ' +
          data.total_relevant +
          ' 条，显示 ' +
          data.returned +
          ' 条'
      }

      this.logLines.value = data.lines.map((l) => this.parseLine(l))
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

  // ── 滚动到底部 ───────────────────────────────────────────
  scrollToBottom(): void {
    if (this.logWrapEl.value) {
      this.logWrapEl.value.scrollTop = this.logWrapEl.value.scrollHeight
    }
  }
}

// 单例
export const logsViewModel = new LogsViewModel()
