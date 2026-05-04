<script setup lang="ts">
import { onMounted, onUnmounted, onActivated, ref, nextTick } from 'vue'
import { overviewViewModel } from './index'
import ModelCard from './ModelCard/ModelCard.vue'
import QdrantCard from './QdrantCard/QdrantCard.vue'
import FlaskCard from './FlaskCard/FlaskCard.vue'
import DeviceCard from './DeviceCard/DeviceCard.vue'

const cumulativeChartRef = ref<HTMLElement | null>(null)
const addedChartRef = ref<HTMLElement | null>(null)
const statTotalDisplayEl = ref<HTMLElement | null>(null)
const statIncrementDisplayEl = ref<HTMLElement | null>(null)
const addedStatDisplayEl = ref<HTMLElement | null>(null)

onMounted(async () => {
  overviewViewModel.cumulativeChartRef.value = cumulativeChartRef.value
  overviewViewModel.addedChartRef.value = addedChartRef.value
  overviewViewModel.statTotalDisplay.value = statTotalDisplayEl.value
  overviewViewModel.statIncrementDisplay.value = statIncrementDisplayEl.value
  overviewViewModel.addedStatDisplay.value = addedStatDisplayEl.value
  await nextTick()
  overviewViewModel.onMounted()
})
onActivated(async () => {
  await nextTick()
  overviewViewModel.redrawCharts()
})
onUnmounted(() => overviewViewModel.onUnmounted())
</script>

<template>
  <div class="overview-wrap">
    <div class="overview-row">
      <ModelCard />
      <QdrantCard />
      <FlaskCard />
      <DeviceCard />
    </div>

    <!-- Memory chart -->
    <div class="chart-section">
      <div class="chart-header">
        <div style="display:flex;align-items:center;gap:10px">
          <div class="chart-title">记忆数据</div>
          <div class="data-tabs">
            <button
              class="data-tab"
              :class="{ active: overviewViewModel.currentDataView.value === 'cumulative' }"
              @click="overviewViewModel.setDataView('cumulative')"
            >累计曲线</button>
            <button
              class="data-tab"
              :class="{ active: overviewViewModel.currentDataView.value === 'added' }"
              @click="overviewViewModel.setDataView('added')"
            >新增曲线</button>
          </div>
        </div>
        <div class="chart-tabs">
          <button
            class="chart-tab"
            :class="{ active: overviewViewModel.currentChartRange.value === 'today' }"
            @click="overviewViewModel.setChartRange('today')"
          >近24小时</button>
          <button
            class="chart-tab"
            :class="{ active: overviewViewModel.currentChartRange.value === 'week' }"
            @click="overviewViewModel.setChartRange('week')"
          >7天</button>
          <button
            class="chart-tab"
            :class="{ active: overviewViewModel.currentChartRange.value === 'month' }"
            @click="overviewViewModel.setChartRange('month')"
          >30天</button>
          <button
            class="chart-tab"
            :class="{ active: overviewViewModel.currentChartRange.value === 'all' }"
            @click="overviewViewModel.setChartRange('all')"
          >全部</button>
        </div>
      </div>

      <!-- Cumulative chart view -->
      <div v-show="overviewViewModel.currentDataView.value === 'cumulative'">
        <div ref="cumulativeChartRef" style="width:100%;height:140px;"></div>
        <div class="chart-stats">
          <div class="stat-box">
            <div class="sb-value" ref="statTotalDisplayEl"></div>
            <div class="sb-label">记忆总数</div>
          </div>
          <div class="stat-box" v-show="overviewViewModel.currentChartRange.value !== 'all'">
            <div class="sb-value" ref="statIncrementDisplayEl">{{ overviewViewModel.statIncrementValue }}</div>
            <div class="sb-label">{{ overviewViewModel.statIncrementLabel }}</div>
          </div>
        </div>
      </div>

      <!-- Added chart view -->
      <div v-show="overviewViewModel.currentDataView.value === 'added'">
        <div ref="addedChartRef" style="width:100%;height:140px;"></div>
        <div class="chart-stats single">
          <div class="stat-box">
            <div class="sb-value" ref="addedStatDisplayEl"></div>
            <div class="sb-label">{{ overviewViewModel.addedStatLabel }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overview-wrap { padding: 24px; flex: 1; display: flex; flex-direction: column; min-height: 0; overflow-y: auto; gap: 20px; box-sizing: border-box; }
.overview-row { display: flex; gap: 12px; flex-wrap: wrap; }

.chart-section { background: #1a1d27; border: 1px solid #2d3149; border-radius: 12px; padding: 20px; flex: 1; display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.chart-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.chart-title { font-size: 13px; font-weight: 600; color: #e2e8f0; }
.chart-tabs { display: flex; gap: 2px; background: #12141c; border-radius: 8px; padding: 2px; }
.chart-tab { padding: 3px 10px; border-radius: 6px; font-size: 11px; color: #64748b; cursor: pointer; transition: all .2s; user-select: none; border: none; background: transparent; }
.chart-tab:hover { color: #94a3b8; }
.chart-tab.active { background: #7c3aed33; color: #a78bfa; font-weight: 600; }
.data-tabs { display: flex; gap: 4px; }
.data-tab { padding: 4px 12px; border-radius: 6px; font-size: 11px; color: #64748b; cursor: pointer; border: none; background: transparent; }
.data-tab.active { background: #7c3aed22; color: #a78bfa; font-weight: 600; }

.chart-stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; padding-top: 16px; border-top: 1px solid #2d3149; }
.chart-stats.single { grid-template-columns: 1fr; }
.stat-box { text-align: center; }
.sb-value { font-size: 22px; font-weight: 700; color: #a78bfa; }
.sb-label { font-size: 11px; color: #64748b; margin-top: 2px; }
</style>
