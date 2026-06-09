/* Token 用量卡片
 *
 * 作用：展示 LLM Token 消耗统计（24h / 7d / 30d）
 * 实现：每 30 秒轮询 /overview/token-usage，ECharts 折线图 + stat-box
 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { useEcharts } from '@/composables/useEcharts'
import { registerCard } from '../CardRegistry'
import TokenCardVue from './TokenCard.vue'

export interface TokenSummary {
  prompt_tokens: number
  completion_tokens: number
  cache_hit_tokens: number
  cache_miss_tokens: number
  total_tokens: number
  cache_hit_rate: number
}

export interface TokenPeriod {
  summary: TokenSummary
  data: { date: string; prompt_tokens: number; completion_tokens: number; cache_hit_tokens: number; total_tokens: number }[]
}

export class TokenCard {
  readonly loading = ref(true)
  readonly activeTab = ref<'24h' | '7d' | '30d'>('24h')
  readonly periods = ref<Record<string, TokenPeriod>>({})
  readonly chartRef = ref<HTMLElement | null>(null)

  private _api = useApi()
  private _chart = useEcharts(this.chartRef)
  private _polling = usePolling(() => this.poll(), 30000, 0)

  async poll(): Promise<void> {
    try {
      const data = await this._api.fetchJson<any>('/overview/token-usage')
      if (data.ok && data.periods) {
        this.periods.value = data.periods
        this.loading.value = false
        this.drawChart()
      }
    } catch (e) {
      console.error('[TokenCard] poll failed:', e)
      this.loading.value = false
    }
  }

  /** 获取当前 Tab 的摘要数据 */
  get currentSummary(): TokenSummary {
    const period = this.periods.value[this.activeTab.value]
    return period?.summary || {
      prompt_tokens: 0, completion_tokens: 0, cache_hit_tokens: 0,
      cache_miss_tokens: 0, total_tokens: 0, cache_hit_rate: 0,
    }
  }

  /** 切换 Tab */
  switchTab(tab: '24h' | '7d' | '30d'): void {
    this.activeTab.value = tab
    this.drawChart()
  }

  /** 绘制 ECharts 折线图 */
  drawChart(): void {
    const period = this.periods.value[this.activeTab.value]
    if (!period?.data?.length) {
      this._chart.setOption({
        grid: { top: 8, right: 60, bottom: 28, left: 48 },
        xAxis: { type: 'category', data: [], axisLabel: { color: '#64748b', fontSize: 10 } },
        yAxis: { type: 'value', show: false },
        series: [],
      })
      return
    }

    const dates = period.data.map(d => d.date)
    const promptData = period.data.map(d => d.prompt_tokens)
    const completionData = period.data.map(d => d.completion_tokens)
    const cacheData = period.data.map(d => d.cache_hit_tokens)
    const totalData = period.data.map(d => d.total_tokens)

    this._chart.setOption({
      grid: { top: 8, right: 60, bottom: 28, left: 48 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1a1d27',
        borderColor: '#2d3149',
        textStyle: { color: '#e2e8f0', fontSize: 11 },
      },
      legend: { show: false },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { color: '#64748b', fontSize: 10, interval: 3 },
        axisLine: { lineStyle: { color: '#2d3149' } },
      },
      yAxis: {
        type: 'value',
        position: 'right',
        axisLabel: { color: '#64748b', fontSize: 10 },
        splitLine: { lineStyle: { color: '#2d314933' } },
      },
      series: [
        { name: '消耗', type: 'line', smooth: true, data: totalData, lineStyle: { width: 2 }, itemStyle: { color: '#a78bfa' }, symbol: 'none' },
        { name: '输入', type: 'line', smooth: true, data: promptData, lineStyle: { width: 1.5 }, itemStyle: { color: '#60a5fa' }, symbol: 'none' },
        { name: '输出', type: 'line', smooth: true, data: completionData, lineStyle: { width: 1.5 }, itemStyle: { color: '#34d399' }, symbol: 'none' },
        { name: '缓存命中', type: 'line', smooth: true, data: cacheData, lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: '#fbbf24' }, symbol: 'none' },
      ],
    })
  }

  /** 格式化数字（千分位） */
  formatNum(n: number): string {
    return n.toLocaleString()
  }

  /** 格式化百分比 */
  formatRate(rate: number): string {
    if (rate <= 0) return '--'
    return (rate * 100).toFixed(1) + '%'
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

export const tokenCard = new TokenCard()
registerCard({
  name: 'token',
  component: TokenCardVue,
  cardClass: tokenCard,
})
