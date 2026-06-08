/* 记忆数据卡片 ViewModel
 *
 * 作用：管理 MemoryCard 的图表绘制、数据获取和统计数字动画
 * 实现：封装 ECharts 配置生成、API 请求、requestAnimationFrame 数字过渡
 */

import { ref } from 'vue'
import { useEcharts } from '@/composables/useEcharts'
import { useApi } from '@/composables/useApi'

export class MemoryCardViewModel {
  // Chart DOM refs（由 MemoryCard.vue 的 onMounted 注入）
  readonly cumulativeChartRef = ref<HTMLElement | null>(null)
  readonly addedChartRef = ref<HTMLElement | null>(null)

  // 统计数字 DOM refs（由 MemoryCard.vue 的 onMounted 注入）
  readonly statTotalDisplay = ref<HTMLElement | null>(null)
  readonly statIncrementDisplay = ref<HTMLElement | null>(null)
  readonly addedStatDisplay = ref<HTMLElement | null>(null)

  // 图表状态
  readonly currentChartRange = ref<'today' | 'week' | 'month' | 'all'>('today')
  readonly currentDataView = ref<'cumulative' | 'added'>('cumulative')

  // 统计标签文字
  readonly statIncrementLabel = ref('24h新增')
  readonly addedStatLabel = ref('24h新增')

  // Private
  private _cumulativeChart = useEcharts(this.cumulativeChartRef)
  private _addedChart = useEcharts(this.addedChartRef)
  private _animTimers: Record<string, number> = {}

  /* animateCount：DOM 元素数字动画
   * 流程：requestAnimationFrame 循环 → 缓动函数过渡 → 更新 el.textContent
   */
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

  /* _getLabelStrategy：计算图表 X 轴标签策略
   * 流程：判断数据是按小时还是按天 → 返回合适的间隔和格式化函数
   */
  private _getLabelStrategy(data: any[]): { interval: number; formatter: (v: string) => string } {
    if (!data?.length) return { interval: 0, formatter: (v: string) => v }
    const first = data[0]?.date || ''
    const isHourly = first.includes(':')
    const len = data.length
    if (isHourly) {
      return { interval: len > 12 ? 2 : 0, formatter: (v: string) => v }
    }
    return { interval: Math.max(0, Math.floor(len / 8) - 1), formatter: (v: string) => v.slice(5) }
  }

  /* _niceStep：计算 Y 轴"漂亮"步长（1-2-5 序列） */
  private _niceStep(rawStep: number): number {
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)))
    const norm = rawStep / mag
    if (norm <= 1) return mag
    if (norm <= 2) return 2 * mag
    if (norm <= 5) return 5 * mag
    return 10 * mag
  }

  /* _buildChartOption：构建 ECharts 配置
   * 流程：应用标签策略 → 计算漂亮 Y 轴边界 → 配置 grid/xAxis/yAxis/series/tooltip
   */
  private _buildChartOption(data: any[], yData: number[], color: string, bottomPx: number) {
    const { interval, formatter } = this._getLabelStrategy(data)
    const yMin = Math.round(Math.min(...yData))
    const yMax = Math.round(Math.max(...yData))
    const range = yMax - yMin

    // range=0（无变化）时只在上方加留白，曲线贴底；避免 interval:0 导致纵轴标签消失
    let axisMin: number, axisMax: number, step: number
    if (range === 0) {
      axisMin = yMin
      axisMax = yMax + 2
      step = 1
    } else {
      step = this._niceStep(range / Math.min(range, 4))
      axisMin = yMin
      axisMax = yMax
    }

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
        min: axisMin, max: axisMax, interval: step,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: '#1a1d27' } },
        axisLabel: {
          color: '#64748b', fontSize: 10,
          formatter: (v: number) => Math.round(v).toString(),
        },
      },
      series: [{
        type: 'line', smooth: true, data: yData,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        areaStyle: { color: color + '11' },
      }],
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1a1d27',
        borderColor: '#2d3149',
        textStyle: { color: '#e2e8f0', fontSize: 11 },
      },
    }
  }

  /* drawCumulativeChart：绘制累计数据图表 */
  drawCumulativeChart(data: any[]): void {
    if (!data?.length) { this._cumulativeChart.clear(); return }
    const totalData = data.map(d => d.total || 0)
    this._cumulativeChart.setOption(this._buildChartOption(data, totalData, '#7c3aed', 36))
  }

  /* drawAddedChart：绘制新增数据图表 */
  drawAddedChart(data: any[]): void {
    if (!data?.length) { this._addedChart.clear(); return }
    const addedData = data.map(d => d.added || 0)
    this._addedChart.setOption(this._buildChartOption(data, addedData, '#22c55e', 24))
  }

  /* fetchAndDrawChart：获取并绘制累计图表
   * 流程：GET /chart-data?range=xxx → 计算区间新增 → 更新统计标签 → 绘制图表
   */
  async fetchAndDrawChart(range: string): Promise<void> {
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/chart-data?range=' + range)
      const data = res.data || []
      if (range !== 'all') {
        let rangeAdded = 0
        data.forEach((d: any) => { rangeAdded += d.added || 0 })
        this.animateCount(this.statIncrementDisplay.value, rangeAdded, 'statIncrement')
        const labels: Record<string, string> = { today: '24h新增', week: '7天新增', month: '30天新增' }
        this.statIncrementLabel.value = labels[range] || '累计'
      }
      this.drawCumulativeChart(data)
    } catch (e) { console.error('[memory-card] chart error:', e) }
  }

  /* fetchAddedChart：获取并绘制新增图表
   * 流程：GET /chart-data → 累加总数 → 更新统计 → 绘制图表
   */
  async fetchAddedChart(): Promise<void> {
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/chart-data?range=' + this.currentChartRange.value)
      const data = res.data || []
      let total = 0
      data.forEach((d: any) => { total += d.added || 0 })
      this.animateCount(this.addedStatDisplay.value, total, 'addedStat')
      const labels: Record<string, string> = { today: '24h新增', week: '7天新增', month: '30天新增', all: '总新增' }
      this.addedStatLabel.value = labels[this.currentChartRange.value] || '新增'
      this.drawAddedChart(data)
    } catch (e) { console.error('[memory-card] added chart error:', e) }
  }

  /* fetchMemoryCount：获取记忆总数并动画显示 */
  async fetchMemoryCount(): Promise<void> {
    const api = useApi()
    try {
      const res = await api.fetchJson<any>('/memory/count')
      this.animateCount(this.statTotalDisplay.value, res.count || 0, 'statTotal')
    } catch (e) { console.error('[memory-card] memory count error:', e) }
  }

  /* setChartRange：切换时间范围
   * 流程：更新 currentChartRange → 按当前视图类型重新请求数据
   */
  setChartRange(range: 'today' | 'week' | 'month' | 'all'): void {
    if (range === this.currentChartRange.value) return
    this.currentChartRange.value = range
    if (this.currentDataView.value === 'added') this.fetchAddedChart()
    else this.fetchAndDrawChart(range)
  }

  /* setDataView：切换视图类型（累计 / 新增）
   * 流程：更新 currentDataView → 按新类型请求数据
   */
  setDataView(view: 'cumulative' | 'added'): void {
    if (view === this.currentDataView.value) return
    this.currentDataView.value = view
    if (view === 'added') this.fetchAddedChart()
    else this.fetchAndDrawChart(this.currentChartRange.value)
  }

  /* redrawCharts：重绘图表（页面切回 / resize 时调用） */
  redrawCharts(): void {
    if (this.currentDataView.value === 'added') this.fetchAddedChart()
    else this.fetchAndDrawChart(this.currentChartRange.value)
    this.fetchMemoryCount()
  }

  /* onMounted：初始化图表数据（由 OverviewViewModel.onMounted 调用） */
  onMounted(): void {
    setTimeout(() => {
      if (this.currentDataView.value === 'added') this.fetchAddedChart()
      else this.fetchAndDrawChart(this.currentChartRange.value)
    }, 0)
    setTimeout(() => this.fetchMemoryCount(), 0)
  }

  /* onUnmounted：清理动画帧（由 OverviewViewModel.onUnmounted 调用） */
  onUnmounted(): void {
    Object.keys(this._animTimers).forEach(k => { cancelAnimationFrame(this._animTimers[k]) })
  }
}

export const memoryCardViewModel = new MemoryCardViewModel()
