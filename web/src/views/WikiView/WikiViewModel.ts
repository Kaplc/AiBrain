/* Wiki视图模型 - 面向对象设计 */

import { ref, computed, nextTick } from 'vue'
import { useWikiStore } from '@/stores/wiki'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

/* ==================== Types ==================== */
export interface ApiWikiFile {
  filename: string
  abs_path: string
  size_bytes: number
  modified: number
  preview: string
  index_status: 'synced' | 'out_of_sync' | 'not_indexed'
}

type SortKey = 'filename' | 'sizeBytes' | 'modified'
type TabType = 'stats' | 'ops' | 'settings'

/* ==================== WikiViewModel ==================== */
export class WikiViewModel {
  // Loading state
  readonly loading = ref(true)
  readonly loadError = ref(false)

  // Tab state
  readonly activeTab = ref<TabType>('stats')

  // Index result
  readonly indexResultMsg = ref<{ type: 'ok' | 'err'; text: string } | null>(null)
  readonly showProgress = ref(false)
  readonly progressLabel = ref('准备中...')
  readonly progressPct = ref('0%')
  readonly progressPctNum = ref(0)
  readonly logLines = ref<string[]>([])
  readonly logWrapEl = ref<HTMLElement | null>(null)

  // Sorting
  readonly sortKey = ref<SortKey>('modified')
  readonly sortAsc = ref(false)

  // Settings form
  readonly formWikiDir = ref('')
  readonly formLightragDir = ref('')
  readonly formLanguage = ref('Chinese')
  readonly formChunkSize = ref(1200)
  readonly formTimeout = ref(30)
  readonly saving = ref(false)

  // Copy toast
  readonly copyToastVisible = ref(false)

  // File data
  readonly rawFiles = ref<ApiWikiFile[]>([])

  // Private
  private _store = useWikiStore()
  private _api = useApi()
  private _toast = useToast()
  private _pollTimer: ReturnType<typeof setInterval> | null = null
  private _lastDone = -1

  /* ==================== Computed ==================== */
  get sortedFiles(): ApiWikiFile[] {
    const arr = [...this.rawFiles.value]
    const key = this.sortKey.value
    const asc = this.sortAsc.value
    arr.sort((a, b) => {
      let va: string | number, vb: string | number
      if (key === 'filename') {
        va = a.filename.toLowerCase()
        vb = b.filename.toLowerCase()
      } else if (key === 'sizeBytes') {
        va = a.size_bytes
        vb = b.size_bytes
      } else {
        va = a.modified
        vb = b.modified
      }
      if (va < vb) return asc ? -1 : 1
      if (va > vb) return asc ? 1 : -1
      return 0
    })
    return arr
  }

  get totalSize(): number {
    return this.rawFiles.value.reduce((s, f) => s + (f.size_bytes || 0), 0)
  }

  get indexStatusText(): { text: string; color: string } {
    if (!this._store.indexed) return { text: '未索引', color: '#fde047' }
    const out = this.rawFiles.value.filter(f => f.index_status !== 'synced').length
    if (out > 0) return { text: '需重建 ' + out + ' 个文件', color: '#f97316' }
    return { text: '已同步', color: '#86efac' }
  }

  sortArrow(key: SortKey): string {
    if (this.sortKey.value !== key) return ''
    return this.sortAsc.value ? ' ▲' : ' ▼'
  }

  /* ==================== Formatting ==================== */
  escHtml(s: string): string {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1048576).toFixed(1) + ' MB'
  }

  formatDate(ts: number): string {
    if (!ts) return '-'
    const d = new Date(ts * 1000)
    const pad = (n: number) => String(n).padStart(2, '0')
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  }

  /* ==================== Data loading ==================== */
  async loadFiles(skipRender = false): Promise<void> {
    this.loading.value = true
    this.loadError.value = false
    try {
      const data = await this._api.fetchJson<{ files: ApiWikiFile[]; indexed: boolean }>('/wiki/list')
      this.rawFiles.value = Array.isArray(data.files) ? data.files : []
      this._store.indexed = data.indexed ?? false
    } catch (e) {
      console.error('[WikiView] loadFiles error:', e)
      this.loadError.value = true
    } finally {
      this.loading.value = false
    }
  }

  async loadSettings(): Promise<void> {
    try {
      const data = await this._api.fetchJson<any>('/wiki/settings')
      if (data.error) return
      this.formWikiDir.value = data.wiki_dir || 'wiki'
      this.formLightragDir.value = data.lightrag_dir || 'rag/lightrag_data'
      this.formLanguage.value = data.language || 'Chinese'
      this.formChunkSize.value = data.chunk_token_size || 1200
      this.formTimeout.value = data.search_timeout || 30
    } catch (e) {
      console.error('[WikiView] loadSettings error:', e)
    }
  }

  /* ==================== Sorting ==================== */
  doSort(key: SortKey): void {
    if (this.sortKey.value === key) {
      this.sortAsc.value = !this.sortAsc.value
    } else {
      this.sortKey.value = key
      this.sortAsc.value = true
    }
  }

  /* ==================== Tab switching ==================== */
  switchTab(tab: TabType): void {
    const prev = this.activeTab.value
    this.activeTab.value = tab
    if (tab === 'settings') this.loadSettings()
    if (tab === 'ops') this.restoreIndexProgress()
    if (prev === 'ops') this.stopPoll()
  }

  /* ==================== Copy path ==================== */
  copyPath(path: string): void {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(path).then(() => {
        this.flashCopyToast()
      })
    } else {
      const ta = document.createElement('textarea')
      ta.value = path
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      this.flashCopyToast()
    }
  }

  flashCopyToast(): void {
    this.copyToastVisible.value = true
    setTimeout(() => { this.copyToastVisible.value = false }, 1200)
  }

  /* ==================== Index progress ==================== */
  async restoreIndexProgress(): Promise<void> {
    try {
      const pdata = await this._api.fetchJson<{ status: string; done: number; total: number; current_file: string }>('/wiki/index-progress')
      if (pdata.status === 'running') {
        this.applyProgress(pdata)
        this.startPoll()
      } else {
        this.applyDone(pdata)
      }
    } catch (e) {
      console.error('[WikiView] restoreIndexProgress error:', e)
    }
  }

  applyProgress(pdata: { done: number; total: number; current_file: string }): void {
    this.showProgress.value = true
    const pct = pdata.total > 0 ? Math.round((pdata.done / pdata.total) * 100) : 0
    this.progressPctNum.value = pct
    this.progressPct.value = pct + '%'
    this.progressLabel.value = (pdata.current_file || '进行中...') + ' (' + pdata.done + '/' + pdata.total + ')'
    this._lastDone = pdata.done
  }

  applyDone(pdata: { status: string; done: number; total: number }): void {
    if (pdata.total > 0) {
      const pct = Math.round((pdata.done / pdata.total) * 100)
      this.progressPctNum.value = pct
      this.progressPct.value = pct + '%'
    } else {
      this.progressPctNum.value = 100
      this.progressPct.value = '100%'
    }
    this.showProgress.value = false
    this.indexResultMsg.value = pdata.status === 'done'
      ? { type: 'ok', text: '索引完成' }
      : pdata.status === 'error'
        ? { type: 'err', text: '索引出错' }
        : null
  }

  startPoll(): void {
    if (this._pollTimer !== null) return
    this._pollTimer = setInterval(async () => {
      try {
        const pdata = await this._api.fetchJson<{ status: string; done: number; total: number; current_file: string }>('/wiki/index-progress')
        if (pdata.status === 'running') {
          this.applyProgress(pdata)
          await this.refreshLog()
          if (pdata.done !== this._lastDone) {
            this._lastDone = pdata.done
            await this.loadFiles(true)
          }
        } else {
          this._lastDone = -1
          this.stopPoll()
          this.applyDone(pdata)
          await this.loadFiles(true)
          await nextTick()
          this.scrollLogBottom()
        }
      } catch (e) {
        console.error('[WikiView] poll error:', e)
      }
    }, 500)
  }

  stopPoll(): void {
    if (this._pollTimer !== null) {
      clearInterval(this._pollTimer)
      this._pollTimer = null
    }
  }

  async refreshLog(): Promise<void> {
    try {
      const data = await this._api.fetchJson<{ lines: string[] }>('/wiki/index-log?lines=20')
      if (data.lines) {
        this.logLines.value = data.lines
        await nextTick()
        this.scrollLogBottom()
      }
    } catch {
      // 日志获取失败不阻塞
    }
  }

  scrollLogBottom(): void {
    if (this.logWrapEl.value) {
      this.logWrapEl.value.scrollTop = this.logWrapEl.value.scrollHeight
    }
  }

  /* ==================== Rebuild index ==================== */
  async rebuildIndex(): Promise<void> {
    this.indexResultMsg.value = null
    this.showProgress.value = true
    this.progressPctNum.value = 0
    this.progressPct.value = '0%'
    this.progressLabel.value = '准备中...'
    this._lastDone = 0

    try {
      const resp = await this._api.fetchJson<any>('/wiki/index')
      if (resp.error) {
        this.showProgress.value = false
        this.indexResultMsg.value = { type: 'err', text: '索引失败: ' + resp.error }
        return
      }
      this.startPoll()
    } catch (e: any) {
      this.showProgress.value = false
      this.indexResultMsg.value = { type: 'err', text: '请求失败: ' + (e.message || String(e)) }
    }
  }

  /* ==================== Save settings ==================== */
  async saveSettings(): Promise<void> {
    this.saving.value = true
    const payload = {
      wiki_dir: this.formWikiDir.value.trim(),
      lightrag_dir: this.formLightragDir.value.trim(),
      language: this.formLanguage.value,
      chunk_token_size: parseInt(String(this.formChunkSize.value)) || 1200,
      search_timeout: parseInt(String(this.formTimeout.value)) || 30,
    }
    try {
      const data = await this._api.postJson<any>('/wiki/settings', payload)
      if (data.ok) {
        this._toast.show('设置已保存')
        await this.loadFiles()
      } else {
        this._toast.show('保存失败: ' + (data.error || '未知错误'), 'error')
      }
    } catch (e: any) {
      this._toast.show('请求失败: ' + (e.message || String(e)), 'error')
    } finally {
      this.saving.value = false
    }
  }

  /* ==================== Lifecycle ==================== */
  async onMounted(): Promise<void> {
    console.log('[WikiView] mounted')
    await this.loadSettings()
    await this.loadFiles()
    this.restoreIndexProgress()
  }

  onUnmounted(): void {
    this.stopPoll()
  }
}

// 单例
export const wikiViewModel = new WikiViewModel()