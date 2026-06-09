<script setup lang="ts">
import { overviewViewModel } from '../index'

const card = overviewViewModel.tokenCard
</script>

<template>
  <div class="status-card token-card">
    <div class="sc-label-row">
      <div class="sc-label">LLM Token 用量</div>
      <div class="tab-group">
        <button
          v-for="tab in (['24h', '7d', '30d'] as const)"
          :key="tab"
          class="chart-tab"
          :class="{ active: card.activeTab.value === tab }"
          @click="card.switchTab(tab)"
        >{{ tab }}</button>
      </div>
      <button class="btn-refresh" @click="card.poll()" title="刷新">↻</button>
    </div>

    <!-- ECharts 折线图 -->
    <div
      :ref="(el: any) => card.chartRef.value = el as HTMLElement"
      class="chart-container"
    ></div>

    <!-- 统计指标 -->
    <div class="chart-stats">
      <div class="stat-box">
        <div class="sb-value">{{ card.formatNum(card.currentSummary.total_tokens) }}</div>
        <div class="sb-label">消耗</div>
      </div>
      <div class="stat-box">
        <div class="sb-value blue">{{ card.formatNum(card.currentSummary.prompt_tokens) }}</div>
        <div class="sb-label">输入</div>
      </div>
      <div class="stat-box">
        <div class="sb-value green">{{ card.formatNum(card.currentSummary.completion_tokens) }}</div>
        <div class="sb-label">输出</div>
      </div>
      <div class="stat-box">
        <div class="sb-value yellow">{{ card.formatNum(card.currentSummary.cache_hit_tokens) }}</div>
        <div class="sb-label">缓存命中</div>
      </div>
    </div>

    <!-- 缓存命中率进度条 -->
    <div class="cache-bar-wrap">
      <span class="cache-label">缓存命中率</span>
      <div class="cache-bar">
        <div
          class="cache-bar-fill"
          :style="{ width: card.currentSummary.cache_hit_rate > 0 ? (card.currentSummary.cache_hit_rate * 100) + '%' : '0%' }"
        ></div>
      </div>
      <span class="cache-rate">{{ card.formatRate(card.currentSummary.cache_hit_rate) }}</span>
    </div>
  </div>
</template>

<style scoped>
.status-card {
  flex: 1;
  min-width: 320px;
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sc-label-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.sc-label {
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 600;
}

/* Tab 切换按钮 */
.tab-group {
  display: flex;
  gap: 4px;
  margin-left: auto;
}

.chart-tab {
  background: none;
  border: 1px solid #2d3149;
  color: #64748b;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 10px;
  cursor: pointer;
  transition: all .15s;
}
.chart-tab:hover {
  border-color: #475569;
  color: #cbd5e1;
}
.chart-tab.active {
  background: #7c3aed22;
  border-color: #7c3aed55;
  color: #a78bfa;
}

/* 刷新按钮 */
.btn-refresh {
  background: none;
  border: 1px solid #2d3149;
  color: #64748b;
  cursor: pointer;
  font-size: 11px;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .2s;
  flex-shrink: 0;
}
.btn-refresh:hover {
  color: #cbd5e1;
  border-color: #475569;
  background: #1e293b;
}

/* 图表容器 */
.chart-container {
  width: 100%;
  height: 140px;
}

/* 统计数字 */
.chart-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid #2d3149;
}

.stat-box {
  text-align: center;
}

.sb-value {
  font-size: 18px;
  font-weight: 700;
  color: #a78bfa;
}
.sb-value.blue { color: #60a5fa; }
.sb-value.green { color: #34d399; }
.sb-value.yellow { color: #fbbf24; }

.sb-label {
  font-size: 10px;
  color: #64748b;
  margin-top: 2px;
}

/* 缓存命中率进度条 */
.cache-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: #64748b;
}

.cache-label {
  flex-shrink: 0;
  white-space: nowrap;
}

.cache-bar {
  flex: 1;
  height: 6px;
  background: #2d3149;
  border-radius: 3px;
  overflow: hidden;
}

.cache-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
  border-radius: 3px;
  transition: width .3s ease;
}

.cache-rate {
  flex-shrink: 0;
  color: #a78bfa;
  font-weight: 600;
  min-width: 40px;
  text-align: right;
}
</style>
