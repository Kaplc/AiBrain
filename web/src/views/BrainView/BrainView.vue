<script setup lang="ts">
/* BrainView — BrainLoop 状态观察台（只读驾驶舱）。
 *
 * 第一版只观察、不控制：无 start/stop/tick/send/save 入口。
 * 自动刷新仅轮询 /brain/state + /brain/runs/recent（GET），detail 按需加载。
 * 全程不调用任何 POST /brain/life/* 接口（安全验收）。
 */
import { onMounted, onUnmounted } from 'vue'
import { brainViewModel as vm } from './BrainViewModel'
import BrainStatusPanel from './components/BrainStatusPanel.vue'
import BrainRunList from './components/BrainRunList.vue'
import BrainRunDetail from './components/BrainRunDetail.vue'
import PendingExpressionPanel from './components/PendingExpressionPanel.vue'
import GateResultPanel from './components/GateResultPanel.vue'

onMounted(() => { void vm.init() })
onUnmounted(() => { vm.destroy() })
</script>

<template>
  <div class="brain-page" data-testid="brain-page">
    <!-- 页头：标题 + 刷新控制 -->
    <header class="page-header">
      <div class="title-wrap">
        <div class="page-title">BrainLoop 观察台</div>
        <div class="page-sub">只读状态面板 · 实时观察后台数字生命循环</div>
      </div>
      <div class="refresh-controls">
        <span class="last-at" v-if="vm.lastRefreshedAt.value">更新于 {{ vm.lastRefreshedAt.value }}</span>
        <button class="ctrl" :class="{ active: !vm.refreshPaused.value }" @click="vm.togglePause()"
          data-testid="brain-autorefresh-toggle" :title="vm.refreshPaused.value ? '恢复自动刷新' : '暂停自动刷新'">
          {{ vm.refreshPaused.value ? '⏸ 自动刷新已暂停' : '● 自动刷新中' }}
        </button>
        <button class="ctrl primary" @click="vm.manualRefresh()" :disabled="vm.loadingState.value || vm.loadingRuns.value"
          data-testid="brain-refresh-btn" title="手动刷新（只读 GET）">
          {{ (vm.loadingState.value || vm.loadingRuns.value) ? '刷新中…' : '↻ 立即刷新' }}
        </button>
      </div>
    </header>

    <!-- 状态概览（满宽） -->
    <BrainStatusPanel />

    <!-- run 列表 + 详情 -->
    <div class="run-row">
      <BrainRunList />
      <BrainRunDetail />
    </div>

    <!-- pending + gate -->
    <div class="bottom-row">
      <PendingExpressionPanel />
      <GateResultPanel />
    </div>

    <!-- 只读声明 -->
    <footer class="page-foot">本面板为只读观察视图，不会触发 LLM、后台 tick、状态写入或主动发送。</footer>
  </div>
</template>

<style scoped>
.brain-page { padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; flex: 1; box-sizing: border-box; overflow-y: auto; }

.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.title-wrap { display: flex; flex-direction: column; gap: 2px; }
.page-title { font-size: 18px; font-weight: 700; color: #e2e8f0; }
.page-sub { font-size: 11px; color: #64748b; }

.refresh-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.last-at { font-size: 10px; color: #64748b; }
.ctrl { background: #1a1d27; border: 1px solid #2d3149; color: #94a3b8; font-size: 11px; padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: all .15s; }
.ctrl:hover:not(:disabled) { border-color: #475569; color: #cbd5e1; }
.ctrl:disabled { opacity: .55; cursor: default; }
.ctrl.active { color: #86efac; border-color: #22c55e44; }
.ctrl.primary { color: #a78bfa; border-color: #7c3aed55; }
.ctrl.primary:hover:not(:disabled) { background: #7c3aed1a; }

.run-row { display: grid; grid-template-columns: 38% 1fr; gap: 14px; align-items: stretch; }
.bottom-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: stretch; }

@media (max-width: 960px) {
  .run-row { grid-template-columns: 1fr; }
  .bottom-row { grid-template-columns: 1fr; }
}

.page-foot { font-size: 10px; color: #475569; text-align: center; padding: 4px 0 2px; }
</style>
