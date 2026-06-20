<script setup lang="ts">
import { onMounted } from 'vue'
import { statsViewModel } from './index'

const vm = statsViewModel

onMounted(() => {
  vm.balance.poll()     // 立即首次刷新
  vm.token.poll()
  vm.balance.start()    // 后续自动轮询
  vm.token.start()
})
</script>

<template>
  <div class="stats-page">
    <div class="page-header">
      <div class="page-title">用量</div>
    </div>
    <div class="stats-grid">
      <!-- 余额卡片 -->
      <div class="stat-card">
        <div class="sc-header">
          <div class="sc-label">DeepSeek 余额</div>
          <span v-if="vm.balance.loading.value" class="badge badge-loading">加载中</span>
          <span v-else-if="vm.balance.error.value" class="badge badge-err" :title="vm.balance.error.value">不可用</span>
          <span v-else-if="vm.balance.available.value" class="badge badge-ok">可用</span>
          <span v-else class="badge badge-err">不可用</span>
          <button class="btn-refresh" @click="vm.balance.poll()" title="刷新">↻</button>
        </div>

        <template v-if="vm.balance.loading.value">
          <div class="balance-val">--</div>
        </template>
        <template v-else-if="vm.balance.error.value">
          <div class="balance-val err">--</div>
          <div class="sub-text" v-if="vm.balance.error.value.includes('API key')">请在 LLM 设置中配置 API Key</div>
        </template>
        <template v-else>
          <div class="balance-val">
            ¥ {{ vm.balance.formatBalance(vm.balance.balanceList.value[0]?.total_balance || '0') }}
          </div>
          <div class="balance-detail">
            <span>赠金: ¥{{ vm.balance.formatBalance(vm.balance.balanceList.value[0]?.granted_balance || '0') }}</span>
            <span>充值: ¥{{ vm.balance.formatBalance(vm.balance.balanceList.value[0]?.topped_up_balance || '0') }}</span>
          </div>
          <div class="today-cost" v-if="vm.balance.todayCost.value">
            <span class="tc-label">今日消耗</span>
            <span class="tc-value">¥{{ vm.balance.todayCost.value.total_cost.toFixed(2) }}</span>
          </div>
        </template>
      </div>

      <!-- Token 用量卡片 -->
      <div class="stat-card token-card">
        <div class="sc-header">
          <div class="sc-label">LLM Token 用量</div>
          <div class="tab-group">
            <button v-for="t in (['24h', '7d', '30d'] as const)" :key="t"
              class="chart-tab" :class="{ active: vm.token.activeTab.value === t }"
              @click="vm.token.switchTab(t)">{{ t }}</button>
          </div>
          <button class="btn-refresh" @click="vm.token.poll()" title="刷新">↻</button>
        </div>

        <div :ref="(el: any) => vm.token.chartRef.value = el as HTMLElement" class="chart-box"></div>

        <div class="stat-row">
          <div class="sb"><div class="sb-v">{{ vm.token.formatNum(vm.token.currentSummary.total_tokens) }}</div><div class="sb-l">消耗</div></div>
          <div class="sb"><div class="sb-v blue">{{ vm.token.formatNum(vm.token.currentSummary.prompt_tokens) }}</div><div class="sb-l">输入</div></div>
          <div class="sb"><div class="sb-v green">{{ vm.token.formatNum(vm.token.currentSummary.completion_tokens) }}</div><div class="sb-l">输出</div></div>
          <div class="sb"><div class="sb-v yellow">{{ vm.token.formatNum(vm.token.currentSummary.cache_hit_tokens) }}</div><div class="sb-l">缓存命中</div></div>
        </div>

        <div class="cache-bar-wrap">
          <span class="cache-label">缓存命中率</span>
          <div class="cache-bar"><div class="cache-fill" :style="{ width: (vm.token.currentSummary.cache_hit_rate * 100) + '%' }"></div></div>
          <span class="cache-rate">{{ vm.token.formatRate(vm.token.currentSummary.cache_hit_rate) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-page { padding: 24px; display: flex; flex-direction: column; gap: 16px; flex: 1; box-sizing: border-box; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { font-size: 18px; font-weight: 700; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 800px) { .stats-grid { grid-template-columns: 1fr; } }

.stat-card {
  background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px;
  padding: 16px 18px; display: flex; flex-direction: column; gap: 8px;
}
.sc-header { display: flex; align-items: center; gap: 6px; width: 100%; }
.sc-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.tab-group { display: flex; gap: 4px; margin-left: auto; }
.chart-tab {
  background: none; border: 1px solid #2d3149; color: #64748b; padding: 2px 10px;
  border-radius: 4px; font-size: 10px; cursor: pointer; transition: all .15s;
}
.chart-tab:hover { border-color: #475569; color: #cbd5e1; }
.chart-tab.active { background: #7c3aed22; border-color: #7c3aed55; color: #a78bfa; }
.btn-refresh {
  background: none; border: 1px solid #2d3149; color: #64748b; cursor: pointer; font-size: 11px;
  width: 22px; height: 22px; border-radius: 4px; display: flex; align-items: center; justify-content: center;
  margin-left: 4px; flex-shrink: 0; transition: all .2s;
}
.btn-refresh:hover { color: #cbd5e1; border-color: #475569; background: #1e293b; }

.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge-ok { background: #22c55e22; color: #86efac; border: 1px solid #22c55e44; }
.badge-err { background: #ef444422; color: #fca5a5; border: 1px solid #ef444444; }
.badge-loading { background: #eab30822; color: #fde68a; border: 1px solid #eab30844; }

.balance-val { font-size: 22px; font-weight: 700; color: #a78bfa; }
.balance-val.err { color: #64748b; }
.balance-detail { display: flex; gap: 16px; font-size: 10px; color: #64748b; }
.sub-text { font-size: 11px; color: #64748b; }
.today-cost { display: flex; align-items: center; gap: 8px; margin-top: 4px; padding-top: 8px; border-top: 1px solid #2d3149; width: 100%; font-size: 11px; }
.tc-label { color: #64748b; }
.tc-value { color: #f59e0b; font-weight: 700; }
.chart-box { width: 100%; height: 140px; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding-top: 12px; border-top: 1px solid #2d3149; }
.sb { text-align: center; }
.sb-v { font-size: 18px; font-weight: 700; color: #a78bfa; }
.sb-v.blue { color: #60a5fa; }
.sb-v.green { color: #34d399; }
.sb-v.yellow { color: #fbbf24; }
.sb-l { font-size: 10px; color: #64748b; margin-top: 2px; }
.cache-bar-wrap { display: flex; align-items: center; gap: 8px; font-size: 10px; color: #64748b; }
.cache-bar { flex: 1; height: 6px; background: #2d3149; border-radius: 3px; overflow: hidden; }
.cache-fill { height: 100%; background: linear-gradient(90deg, #7c3aed, #a78bfa); border-radius: 3px; transition: width .3s ease; }
.cache-rate { flex-shrink: 0; color: #a78bfa; font-weight: 600; min-width: 40px; text-align: right; }
</style>
