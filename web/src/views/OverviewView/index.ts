/* 总览视图模型 - 组合各卡片类 */

import { ref } from 'vue'
import { useEcharts } from '@/composables/useEcharts'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { getAllCards } from './CardRegistry'

/* ==================== 类型 ==================== */
export type ModelBadge = 'loading' | 'ok' | 'err'
export type QdrantBadge = 'loading' | 'ok' | 'err'
export type FlaskBadge = 'ok' | 'err' | 'restarting' | 'yellow'

export interface ModelCardData {
  loaded: boolean
  embedding_model?: string
  embedding_dim?: number
}

export interface QdrantCardData {
  ready: boolean
  host: string
  port: number
  disk_size?: number
}

export interface FlaskCardData {
  pid: number
  port: number
  uptime?: number
}

export interface SystemInfo {
  cpu_percent?: number
  memory_percent?: number
  gpu_name?: string
}

/* ==================== ModelCard ==================== */
export class ModelCard {
  readonly badge = ref<ModelBadge>('loading')
  readonly subText = ref('加载中...')
  readonly detail = ref('')

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 0)

  badgeClass(): string {
    if (this.badge.value === 'loading') return 'badge-loading'
    if (this.badge.value === 'ok') return 'badge-ok'
    return 'badge-err'
  }

  updateFromData(data: ModelCardData): void {
    if (data.loaded) {
      this.badge.value = 'ok'
      this.subText.value = '模型就绪'
      this.detail.value = data.embedding_model ? `${data.embedding_model} · ${data.embedding_dim}d` : ''
    } else {
      this.badge.value = 'loading'
      this.subText.value = '加载中...'
      this.detail.value = ''
    }
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/model')
      this.updateFromData(st)
    } catch {
      this.badge.value = 'err'
      this.subText.value = '模型加载失败'
      this.detail.value = ''
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

/* ==================== QdrantCard ==================== */
export class QdrantCard {
  readonly badge = ref<QdrantBadge>('loading')
  readonly detail = ref('')

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 800)

  badgeClass(): string {
    if (this.badge.value === 'loading') return 'badge-loading'
    if (this.badge.value === 'ok') return 'badge-ok'
    return 'badge-err'
  }

  updateFromData(data: QdrantCardData): void {
    this.badge.value = data.ready ? 'ok' : 'err'
    if (data.ready) {
      const sizeGB = (data.disk_size / (1024**3)).toFixed(1)
      this.detail.value = `${data.host}:${data.port} · ${sizeGB}GB`
    } else {
      this.detail.value = ''
    }
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/qdrant')
      this.updateFromData(st)
    } catch {
      this.badge.value = 'err'
      this.detail.value = '连接失败'
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

/* ==================== FlaskCard ==================== */
export class FlaskCard {
  readonly badge = ref<FlaskBadge>('ok')
  readonly restarting = ref(false)
  readonly restartSeconds = ref(0)
  readonly detail = ref('')
  readonly uptime = ref(0)
  private _restartTimer: number | null = null

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 1600)

  badgeClass(): string {
    if (this.badge.value === 'ok') return 'badge-ok'
    if (this.badge.value === 'restarting') return 'badge-loading'
    return 'badge-err'
  }

  updateFromData(data: FlaskCardData): void {
    this.badge.value = 'ok'
    this.detail.value = `PID: ${data.pid} · 端口: ${data.port}`
    this.uptime.value = data.uptime || 0
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/flask')
      this.updateFromData(st)
    } catch { /* ignore */ }
  }

  async restart(): Promise<void> {
    if (this.restarting.value) return
    this.restarting.value = true
    this.restartSeconds.value = 0
    try {
      await this._api.postJson('/overview/flask/restart', {})
      const countdown = setInterval(() => {
        this.restartSeconds.value++
        if (this.restartSeconds.value >= 15) {
          clearInterval(countdown)
          this.restarting.value = false
        }
      }, 1000)
      this._restartTimer = countdown
    } catch {
      this.restarting.value = false
    }
  }

  cleanup(): void {
    if (this._restartTimer !== null) {
      clearInterval(this._restartTimer)
      this._restartTimer = null
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

/* ==================== DeviceCard ==================== */
export class DeviceCard {
  readonly info = ref<SystemInfo | null>(null)

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 1000, 500)

  updateFromData(data: SystemInfo): void {
    this.info.value = { ...this.info.value, ...data }
  }

  async poll(): Promise<void> {
    try {
      const info = await this._api.fetchJson<SystemInfo>('/overview/system-info')
      this.updateFromData(info)
    } catch { /* ignore */ }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

/* ==================== OverviewViewModel ==================== */
export class OverviewViewModel {
  // Chart refs
  readonly cumulativeChartRef = ref<HTMLElement | null>(null)
  readonly addedChartRef = ref<HTMLElement | null>(null)

  // 卡片实例
  readonly modelCard = new ModelCard()
  readonly qdrantCard = new QdrantCard()
  readonly flaskCard = new FlaskCard()
  readonly deviceCard = new DeviceCard()

  // 从注册表获取卡片列表（用于动态渲染）
  readonly cardList = getAllCards()

  // Chart state
  readonly currentChartRange = ref<'today' | 'week' | 'month' | 'all'>('today')
  readonly currentDataView = ref<'cumulative' | 'added'>('cumulative')
  readonly chartData = ref<any[]>([])
  readonly addedChartData = ref<any[]>([])

  // Stats
  readonly statTotalValue = ref(0)
  readonly statTotalDisplay = ref(0)
  readonly statIncrementValue = ref(0)
  readonly statIncrementDisplay = ref<HTMLElement | null>(null)
  readonly statIncrementLabel = ref('24h新增')
  readonly addedStatDisplay = ref<HTMLElement | null>(null)
  readonly addedStatValue = ref(0)
  readonly addedStatLabel = ref('24h新增')

  // Private
  private _cumulativeChart = useEcharts(this.cumulativeChartRef)
  private _addedChart = useEcharts(this.addedChartRef)
  private _animTimers: Record<string, number> = {}

  formatUptime(seconds: number): string {
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d > 0) return `${d}天${h}时`
    if (h > 0) return `${h}时${m}分`
    return `${m}分`
  }

  animateCount(el: HTMLElement | null, target: number, key: string): void {
    if (!el) return
    if (this._animTimers[key]) cancelAnimationFrame(this._animTimers[key])
    const start = parseInt(el.textContent || '0', 10) || 0
    if (start === target) return
    const duration = 600
    const startTime = performance.now()

    const step = (now: number) => {
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      el.textContent = Math.round(start + (target - start) * eased).toLocaleString()
      if (progress < 1) {
        this._animTimers[key] = requestAnimationFrame(step)
      } else {
        delete this._animTimers[key]
      }
    }
    this._animTimers[key] = requestAnimationFrame(step)
  }

  private _getLabelStrategy(data: any[]): { interval: number; formatter: (v: string) => string } {
    if (!data?.length) return { interval: 0, formatter: (v: string) => v }
    const first = data[0]?.date || ''
    const isHourly = first.includes(':')
    const len = data.length
    if (isHourly) {
      // 24小时：每小时一个点，间隔2显示每3小时 (06:00, 09:00, 12:00...)
      return { interval: len > 12 ? 2 : 0, formatter: (v: string) => v }
    }
    // 7天/30天：按天显示，间隔取整避免太密
    const dayInterval = Math.max(0, Math.floor(len / 8) - 1)
    return { interval: dayInterval, formatter: (v: string) => v.slice(5) }
  }

  private _buildChartOption(data: any[], yData: number[], color: string, bottomPx: number) {
    const { interval, formatter } = this._getLabelStrategy(data)
    return {
      grid: { top: 8, right: 60, bottom: bottomPx, left: 48 },
      xAxis: {
        type: 'category',
        data: data.map(d => d.date || ''),
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#2d3149' } },
        axisLabel: { color: '#64748b', fontSize: 10, interval, rotate: 0, formatter },
        axisTick: { show: true, align: 'center' },
      },
      yAxis: {
        type: 'value', position: 'right',
        splitLine: { lineStyle: { color: '#1a1d27' } },
        axisLabel: { color: '#64748b', fontSize: 10 },
        scale: true,
        splitNumber: 4,
      },
      series: [{
        name: yData === data.map(d => d.total || 0) ? '累计' : '新增',
        type: 'line', smooth: true, data: yData,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        areaStyle: { color: color + '11' },
      }],
      tooltip: { trigger: 'axis', backgroundColor: '#1a1d27', borderColor: '#2d3149', textStyle: { color: '#e2e8f0', fontSize: 11 } },
    }
  }

  drawCumulativeChart(data: any[]): void {
    if (!data?.length) { this._cumulativeChart.clear(); return }
    const totalData = data.map(d => d.total || 0)
    const opt = this._buildChartOption(data, totalData, '#7c3aed', 36)
    this._cumulativeChart.setOption(opt)
  }

  drawAddedChart(data: any[]): void {
    if (!data?.length) { this._addedChart.clear(); return }
    const addedData = data.map(d => d.added || 0)
    const opt = this._buildChartOption(data, addedData, '#22c55e', 24)
    this._addedChart.setOption(opt)
  }

  async fetchAndDrawChart(range: string): Promise<void> {
    const { useApi } = await import('@/composables/useApi')
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/chart-data?range=' + range)
      const data = res.data || []
      if (range !== 'all') {
        let rangeAdded = 0
        data.forEach((d: any) => { rangeAdded += d.added || 0 })
        this.animateCount(this.statIncrementDisplay.value, rangeAdded, 'statIncrement')
        this.statIncrementValue.value = rangeAdded
        const labels: Record<string, string> = { today: '24h新增', week: '7天新增', month: '30天新增' }
        this.statIncrementLabel.value = labels[range] || '累计'
      }
      this.drawCumulativeChart(data)
    } catch (e) { console.error('[overview] chart error:', e) }
  }

  async fetchAddedChart(): Promise<void> {
    const { useApi } = await import('@/composables/useApi')
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/chart-data?range=' + this.currentChartRange.value)
      const data = res.data || []
      let total = 0
      data.forEach((d: any) => { total += d.added || 0 })
      this.animateCount(this.addedStatDisplay.value, total, 'addedStat')
      this.addedStatValue.value = total
      const labels: Record<string, string> = { today: '24h新增', week: '7天新增', month: '30天新增', all: '总新增' }
      this.addedStatLabel.value = labels[this.currentChartRange.value] || '新增'
      this.drawAddedChart(data)
    } catch (e) { console.error('[overview] added chart error:', e) }
  }

  async fetchMemoryCount(): Promise<void> {
    const { useApi } = await import('@/composables/useApi')
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/memory/count')
      this.animateCount(this.statTotalDisplay.value, res.count || 0, 'statTotal')
      this.statTotalValue.value = res.count || 0
    } catch (e) { console.error('[overview] memory count error:', e) }
  }

  setChartRange(range: 'today' | 'week' | 'month' | 'all'): void {
    if (range === this.currentChartRange.value) return
    this.currentChartRange.value = range
    if (this.currentDataView.value === 'added') this.fetchAddedChart()
    else this.fetchAndDrawChart(range)
  }

  setDataView(view: 'cumulative' | 'added'): void {
    if (view === this.currentDataView.value) return
    this.currentDataView.value = view
    if (view === 'added') this.fetchAddedChart()
    else this.fetchAndDrawChart(this.currentChartRange.value)
  }

  onMounted(): void {
    this.modelCard.start()
    this.qdrantCard.start()
    this.flaskCard.start()
    this.deviceCard.start()
    setTimeout(() => this.fetchAndDrawChart(this.currentChartRange.value), 0)
    setTimeout(() => this.fetchMemoryCount(), 0)
  }

  onUnmounted(): void {
    Object.keys(this._animTimers).forEach(k => { cancelAnimationFrame(this._animTimers[k]) })
    this.flaskCard.cleanup()
    this.modelCard.stop()
    this.qdrantCard.stop()
    this.flaskCard.stop()
    this.deviceCard.stop()
  }

  redrawCharts(): void {
    this.fetchAndDrawChart(this.currentChartRange.value)
    this.fetchMemoryCount()
  }
}

export const overviewViewModel = new OverviewViewModel()
