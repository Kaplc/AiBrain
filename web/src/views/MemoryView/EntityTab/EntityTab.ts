import { ref, type Ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

export interface EntityStats {
  entity_nodes: number
  mentions: number
  memory_relations: number
  typed_entity_relations: number
  entity_relations: number
  graph_loaded: boolean
  graph_nodes: number
  graph_edges: number
}

export interface RebuildState {
  status: 'idle' | 'running' | 'completed' | 'failed'
  started_at: string | null
  finished_at: string | null
  total: number
  processed: number
  success: number
  empty: number
  failed: number
  retry_success: number
  current_phase: 'idle' | 'init' | 'first_pass' | 'retry' | 'finished'
  workers: number
  llm_calls: number
  llm_calls_success: number
  llm_calls_failed: number
  progress_pct: number
  elapsed_seconds: number
  error: string | null
}

const EMPTY_REBUILD_STATE: RebuildState = {
  status: 'idle',
  started_at: null,
  finished_at: null,
  total: 0,
  processed: 0,
  success: 0,
  empty: 0,
  failed: 0,
  retry_success: 0,
  current_phase: 'idle',
  workers: 5,
  llm_calls: 0,
  llm_calls_success: 0,
  llm_calls_failed: 0,
  progress_pct: 0,
  elapsed_seconds: 0,
  error: null,
}

export class EntityTab {
  readonly loading = ref(false)
  readonly stats = ref<EntityStats>({
    entity_nodes: 0,
    mentions: 0,
    memory_relations: 0,
    typed_entity_relations: 0,
    entity_relations: 0,
    graph_loaded: false,
    graph_nodes: 0,
    graph_edges: 0,
  })

  readonly rebuildState: Ref<RebuildState> = ref({ ...EMPTY_REBUILD_STATE })
  readonly rebuildLog: Ref<string[]> = ref([])
  readonly rebuildLogVisible = ref(false)
  private _pollHandle: number | null = null
  private _tickHandle: number | null = null

  private _api = useApi()
  private _toast = useToast()

  async loadStats(): Promise<void> {
    this.loading.value = true
    try {
      const data = await this._api.fetchJson<EntityStats>('/memory/entity/stats')
      // 增量更新字段，保持对象引用不变，让 Vue 只 patch 真正变化的 DOM 节点
      Object.assign(this.stats.value, data)
    } catch (e: any) {
      this._toast.show('加载实体统计失败: ' + e.message)
    } finally {
      this.loading.value = false
    }
  }

  /** 静默刷新（轮询用）：不切 loading、不弹错误 toast，避免整个统计块闪烁 */
  async refreshStatsQuiet(): Promise<void> {
    try {
      const data = await this._api.fetchJson<EntityStats>('/memory/entity/stats')
      Object.assign(this.stats.value, data)
    } catch {
      // 静默
    }
  }

  async loadRebuildStatus(): Promise<void> {
    try {
      const data = await this._api.fetchJson<RebuildState>('/memory/graph/rebuild')
      this.rebuildState.value = { ...EMPTY_REBUILD_STATE, ...data }
    } catch {
      // 静默
    }
  }

  private _startPolling() {
    if (this._pollHandle !== null) return
    this._pollHandle = window.setInterval(() => this._pollOnce(), 2000)
    this._startTicker()
  }

  private _stopPolling() {
    if (this._pollHandle !== null) {
      clearInterval(this._pollHandle)
      this._pollHandle = null
    }
    this._stopTicker()
  }

  /** 每秒本地累加 elapsed_seconds，避免依赖 2s 轮询产生跳秒 */
  private _startTicker() {
    if (this._tickHandle !== null) return
    this._tickHandle = window.setInterval(() => {
      if (this.rebuildState.value.status !== 'running') return
      this.rebuildState.value.elapsed_seconds += 1
    }, 1000)
  }

  private _stopTicker() {
    if (this._tickHandle !== null) {
      clearInterval(this._tickHandle)
      this._tickHandle = null
    }
  }

  private async _pollOnce() {
    await this.loadRebuildStatus()
    // 静默刷新统计卡片：只 patch 变化的字段，不切 loading 状态，
    // 避免 v-if="tab.loading.value" 触发整块重渲染
    await this.refreshStatsQuiet()
    if (this.rebuildState.value.status !== 'running') {
      this._stopPolling()
      if (this.rebuildState.value.status === 'completed') {
        this._toast.show('实体网络重建完成')
      } else if (this.rebuildState.value.status === 'failed') {
        this._toast.show('实体网络重建失败：' + (this.rebuildState.value.error || '未知错误'))
      }
    }
  }

  /** Tab 挂载时调用：恢复后台状态 + 必要时启动轮询 */
  async onTabMounted(): Promise<void> {
    await this.loadStats()
    await this.loadRebuildStatus()
    if (this.rebuildState.value.status === 'running') {
      this._startPolling()
    }
  }

  onTabUnmounted(): void {
    this._stopPolling()
    this._stopTicker()
  }

  async startRebuild(): Promise<boolean> {
    try {
      await this._api.fetchJson('/memory/graph/rebuild', {
        method: 'POST',
        body: JSON.stringify({ workers: 5, batch_size: 10, delay: 1.0 }),
      })
      this._toast.show('已开始重建实体网络')
      await this.loadRebuildStatus()
      this._startPolling()
      return true
    } catch (e: any) {
      this._toast.show('启动失败：' + (e?.message || '未知错误'))
      return false
    }
  }

  async cancelRebuild(): Promise<void> {
    try {
      await this._api.fetchJson('/memory/graph/rebuild/cancel', {
        method: 'POST',
        body: '{}',
      })
      this._toast.show('已发送取消指令')
    } catch (e: any) {
      this._toast.show('取消失败：' + (e?.message || '未知错误'))
    }
  }

  async loadRebuildLog(): Promise<void> {
    try {
      const data = await this._api.fetchJson<{ lines: string[]; returned: number }>(
        '/memory/graph/rebuild/log',
        { query: { lines: 100 } }
      )
      this.rebuildLog.value = data.lines ?? []
    } catch {
      this.rebuildLog.value = []
    }
  }

  toggleLogPanel(): void {
    this.rebuildLogVisible.value = !this.rebuildLogVisible.value
    if (this.rebuildLogVisible.value) {
      this.loadRebuildLog()
    }
  }
}
