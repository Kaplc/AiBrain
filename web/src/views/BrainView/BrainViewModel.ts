/* BrainViewModel — BrainLoop 状态面板的只读状态层
 *
 * 职责：封装 /brain/state、/brain/runs/recent、/brain/runs/<id> 三个只读 GET，
 * 维护各模块独立的 loading/error，自动刷新只刷新 state+recent（不刷 detail），
 * 手动刷新同理。全程不调用 /brain/life/*（start/stop/tick）——这些是带副作用控制接口。
 *
 * 设计要点（plan 第七节流程 + 安全验收）：
 *   - 自动刷新间隔 >= 3000ms（这里用 4000ms，10s 内最多 ~2.5 轮，远低于 5 轮上限）。
 *   - detail 仅在用户点击 run 时请求；刷新时保留已选 run 面板不清空。
 *   - 任何接口失败只置对应 error，不影响其他模块，不白屏。
 */
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  BrainStateResponse, BrainRunSummary, BrainRunDetail, ModeFilter, PendingExpression,
} from './types'

// 自动刷新间隔：plan 非功能要求 >=3000ms，取 4000ms 既够实时又不压后端
const REFRESH_INTERVAL = 4000

class BrainViewModel {
  // ── 响应数据 ─────────────────────────────────────────────
  state = ref<BrainStateResponse | null>(null)
  runs = ref<BrainRunSummary[]>([])
  selectedRun = ref<BrainRunDetail | null>(null)
  selectedRunId = ref<string>('')

  // ── 前端控制状态 ─────────────────────────────────────────
  modeFilter = ref<ModeFilter>('all')
  refreshPaused = ref(false)
  lastRefreshedAt = ref<string>('')

  // ── 各模块独立 loading / error ──────────────────────────
  loadingState = ref(false)
  loadingRuns = ref(false)
  loadingDetail = ref(false)
  errorState = ref('')
  errorRuns = ref('')
  errorDetail = ref('')

  private api = useApi()
  private timer: number | null = null

  // ── 便捷 computed（组件直接用）──────────────────────────
  get life() {
    return computed(() => this.state.value?.life_state ?? null)
  }
  get config() {
    return computed(() => this.state.value?.config ?? null)
  }
  get schedulerRunning() {
    return computed(() => !!this.state.value?.scheduler_running)
  }
  get pendings() {
    return computed<PendingExpression[]>(() => this.state.value?.life_state?.pending_expressions ?? [])
  }
  get hasStateError() {
    // 后端预热/异常时 /brain/state 会带 error 字段（状态码 500 body）
    return computed(() => !!(this.state.value?.error) || !!this.errorState.value)
  }

  // ── 拉取：state ─────────────────────────────────────────
  async loadState(): Promise<void> {
    this.loadingState.value = true
    this.errorState.value = ''
    try {
      const data = await this.api.fetchJson<BrainStateResponse>('/brain/state')
      this.state.value = data
      if (data?.error) this.errorState.value = data.error
    } catch (e: any) {
      this.errorState.value = this._errMsg(e)
    } finally {
      this.loadingState.value = false
    }
  }

  // ── 拉取：recent runs ───────────────────────────────────
  async loadRecent(): Promise<void> {
    this.loadingRuns.value = true
    this.errorRuns.value = ''
    try {
      const query: Record<string, string | number> = { limit: 20 }
      if (this.modeFilter.value !== 'all') query.mode = this.modeFilter.value
      const data = await this.api.fetchJson<{ runs: BrainRunSummary[] }>('/brain/runs/recent', { query })
      this.runs.value = data?.runs ?? []
      if ((data as any)?.error) this.errorRuns.value = (data as any).error
    } catch (e: any) {
      this.errorRuns.value = this._errMsg(e)
      this.runs.value = []
    } finally {
      this.loadingRuns.value = false
    }
  }

  // ── 拉取：run 详情（按需）──────────────────────────────
  async loadDetail(runId: string): Promise<void> {
    if (!runId) return
    this.selectedRunId.value = runId
    this.loadingDetail.value = true
    this.errorDetail.value = ''
    try {
      const data = await this.api.fetchJson<BrainRunDetail>(`/brain/runs/${encodeURIComponent(runId)}`)
      if (data?.error) {
        this.errorDetail.value = data.error
        this.selectedRun.value = null
      } else {
        this.selectedRun.value = data
      }
    } catch (e: any) {
      this.errorDetail.value = this._errMsg(e)
      this.selectedRun.value = null
    } finally {
      this.loadingDetail.value = false
    }
  }

  // ── 交互 ────────────────────────────────────────────────
  /** 点击 run：加载详情。重复点击当前已选则刷新该详情。 */
  selectRun(runId: string): void {
    if (!runId) return
    this.loadDetail(runId)
  }

  /** 切换 mode 过滤后立即重拉 recent。 */
  setModeFilter(mode: ModeFilter): void {
    if (this.modeFilter.value === mode) return
    this.modeFilter.value = mode
    this.loadRecent()
  }

  /** 手动刷新：只刷 state + recent，保留已选 detail 面板。 */
  async manualRefresh(): Promise<void> {
    await Promise.all([this.loadState(), this.loadRecent()])
    this.lastRefreshedAt.value = this._nowClock()
  }

  togglePause(): void {
    this.refreshPaused.value = !this.refreshPaused.value
    if (this.refreshPaused.value) {
      this._stopTimer()
    } else {
      this._startTimer()
    }
  }

  // ── 生命周期（组件 onMounted/onUnmounted 调用）──────────
  async init(): Promise<void> {
    // 首屏：并发拉 state + recent
    await Promise.all([this.loadState(), this.loadRecent()])
    this.lastRefreshedAt.value = this._nowClock()
    this._startTimer()
  }

  destroy(): void {
    this._stopTimer()
  }

  // ── 轮询内部 ────────────────────────────────────────────
  private _startTimer(): void {
    if (this.timer !== null || this.refreshPaused.value) return
    this.timer = window.setInterval(() => {
      // 自动刷新只刷 state + recent；detail 不动（plan 流程约定）
      void this.loadState()
      void this.loadRecent()
      this.lastRefreshedAt.value = this._nowClock()
    }, REFRESH_INTERVAL)
  }

  private _stopTimer(): void {
    if (this.timer !== null) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  // ── 展示格式化（组件共用，集中在这里避免重复）────────────
  /** idle_seconds → 「1h 5m」「5m 0s」「120s」可读形态。 */
  formatSeconds(s: number | undefined | null): string {
    const v = Number(s)
    if (!Number.isFinite(v) || v < 0) return '--'
    const sec = Math.floor(v)
    if (sec < 60) return `${sec}s`
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const r = sec % 60
    if (h > 0) return `${h}h ${m}m`
    return `${m}m ${r}s`
  }

  /** 分数 → 2 位小数字符串。 */
  formatScore(v: number | undefined | null): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '--'
    return n.toFixed(2)
  }

  /** 0~1 → 百分比整数。 */
  formatPct(v: number | undefined | null): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '--'
    return `${Math.round(n * 100)}%`
  }

  /** 截断长文本。 */
  truncate(s: any, n = 60): string {
    const t = s == null ? '' : String(s)
    return t.length > n ? t.slice(0, n) + '…' : t
  }

  /** iso 时间 → 本地可读时间；空或坏值返回 '--'。 */
  formatTime(iso: any): string {
    if (!iso) return '--'
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return '--'
      return d.toLocaleString()
    } catch {
      return '--'
    }
  }

  // ── 小工具 ──────────────────────────────────────────────
  private _errMsg(e: any): string {
    if (!e) return '请求失败'
    return e?.message || String(e)
  }

  private _nowClock(): string {
    // 仅用于展示「上次刷新时间」，本地时钟即可
    try {
      return new Date().toLocaleTimeString()
    } catch {
      return ''
    }
  }
}

export const brainViewModel = new BrainViewModel()
