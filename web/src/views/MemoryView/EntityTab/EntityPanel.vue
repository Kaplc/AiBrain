<script setup lang="ts">
import { onMounted, onBeforeUnmount, computed } from 'vue'
import { memoryViewModel } from '../index'

const vm = memoryViewModel
const tab = vm.entityTab

const state = tab.rebuildState
const isRunning = computed(() => state.value.status === 'running')
const isCompleted = computed(() => state.value.status === 'completed')
const isFailed = computed(() => state.value.status === 'failed')
const isIdle = computed(() => state.value.status === 'idle')

const llmSuccessRate = computed(() => {
  const total = state.value.llm_calls
  if (!total) return '—'
  return Math.round((state.value.llm_calls_success / total) * 100)
})

const phaseLabel = computed(() => {
  const map: Record<string, string> = {
    init: '初始化',
    first_pass: '第一轮提取',
    retry: '重试空记忆',
    finished: '已完成',
    idle: '空闲',
  }
  return map[state.value.current_phase] || state.value.current_phase
})

function formatSeconds(s: number) {
  if (!s) return '0s'
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m}m${sec}s` : `${sec}s`
}

onMounted(() => {
  // 由父组件 switchTab('entity') 触发；此处仅作直接挂载（如测试）的兜底
  if (vm.currentTab.value === 'entity') tab.onTabMounted()
})
onBeforeUnmount(() => tab.onTabUnmounted())
</script>

<template>
  <div class="entity-panel">
    <div class="entity-toolbar">
      <span class="entity-title">实体统计</span>
      <div class="toolbar-actions">
        <button
          class="btn-rebuild"
          :class="{ running: isRunning }"
          :disabled="isRunning"
          @click="tab.startRebuild()"
          :title="isRunning ? '正在运行中' : '清空图数据库并重新提取所有实体的关联关系'"
        >
          <span v-if="isRunning" class="dot-pulse"></span>
          {{ isRunning ? '重建中...' : '重建实体网络' }}
        </button>
        <button
          v-if="isRunning"
          class="btn-cancel"
          @click="tab.cancelRebuild()"
          title="取消当前任务"
        >取消</button>
        <button class="btn-refresh" @click="tab.loadStats()" :disabled="tab.loading.value">
          {{ tab.loading.value ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="entity-content">
      <!-- 进度卡片：仅在 running / completed / failed 时显示 -->
      <div v-if="!isIdle" class="rebuild-card" :class="state.status">
        <div class="rebuild-header">
          <span class="rebuild-status">
            <span v-if="isRunning" class="status-dot running"></span>
            <span v-else-if="isCompleted" class="status-dot done"></span>
            <span v-else-if="isFailed" class="status-dot failed"></span>
            {{ isRunning ? '正在重建' : isCompleted ? '已完成' : '失败' }}
          </span>
          <span class="rebuild-phase">{{ phaseLabel }}</span>
          <span class="rebuild-elapsed">耗时 {{ formatSeconds(state.elapsed_seconds) }}</span>
        </div>

        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: state.progress_pct + '%' }"></div>
        </div>
        <div class="progress-text">
          {{ state.processed }} / {{ state.total }} ({{ state.progress_pct }}%)
        </div>

        <div class="rebuild-stats">
          <div class="rs-item"><span class="rs-label">成功</span><span class="rs-val success">{{ state.success }}</span></div>
          <div class="rs-item"><span class="rs-label">空</span><span class="rs-val warn">{{ state.empty }}</span></div>
          <div class="rs-item"><span class="rs-label">失败</span><span class="rs-val fail">{{ state.failed }}</span></div>
          <div class="rs-item"><span class="rs-label">重试成功</span><span class="rs-val accent">{{ state.retry_success }}</span></div>
          <div class="rs-item"><span class="rs-label">线程数</span><span class="rs-val">{{ state.workers }}</span></div>
          <div class="rs-item rs-item-wide">
            <span class="rs-label">模型调用</span>
            <span class="rs-val">{{ state.llm_calls }} 次
              <span class="rs-sub">(成功 {{ state.llm_calls_success }} / 失败 {{ state.llm_calls_failed }})</span>
            </span>
          </div>
          <div class="rs-item"><span class="rs-label">LLM 成功率</span><span class="rs-val accent">{{ llmSuccessRate }}%</span></div>
        </div>

        <div v-if="isFailed && state.error" class="rebuild-error">
          <strong>错误：</strong>{{ state.error }}
        </div>

        <div class="rebuild-log-toggle">
          <button class="btn-link" @click="tab.toggleLogPanel()">
            {{ tab.rebuildLogVisible.value ? '收起日志' : '查看日志末尾 100 行' }}
          </button>
        </div>

        <div v-if="tab.rebuildLogVisible.value" class="rebuild-log">
          <div v-if="tab.rebuildLog.value.length === 0" class="log-empty">暂无日志</div>
          <div v-for="(line, i) in tab.rebuildLog.value" :key="i" class="log-line">{{ line }}</div>
        </div>
      </div>

      <div v-if="tab.loading.value" class="entity-loading">加载中...</div>
      <template v-else>
        <div class="stat-cards">
          <div class="stat-card">
            <div class="stat-value">{{ tab.stats.value.entity_nodes }}</div>
            <div class="stat-label">实体数量</div>
            <div class="stat-sub">entity_nodes</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ tab.stats.value.mentions }}</div>
            <div class="stat-label">提及记录</div>
            <div class="stat-sub">mentions</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ tab.stats.value.memory_relations }}</div>
            <div class="stat-label">记忆关系</div>
            <div class="stat-sub">memory_relations</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ tab.stats.value.entity_relations }}</div>
            <div class="stat-label">实体关系</div>
            <div class="stat-sub">entity_relations</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ tab.stats.value.typed_entity_relations }}</div>
            <div class="stat-label">类型关系</div>
            <div class="stat-sub">typed_entity_relations</div>
          </div>
        </div>

        <div class="graph-status-card">
          <div class="status-header">内存图状态</div>
          <div class="status-body">
            <span class="status-dot" :class="{ loaded: tab.stats.value.graph_loaded }"></span>
            <span class="status-text">{{ tab.stats.value.graph_loaded ? '已加载' : '未加载' }}</span>
            <span class="status-divider">|</span>
            <span class="status-info">节点: {{ tab.stats.value.graph_nodes }}</span>
            <span class="status-divider">|</span>
            <span class="status-info">边: {{ tab.stats.value.graph_edges }}</span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.entity-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.entity-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(100, 120, 200, 0.15);
  flex-shrink: 0;
  background: rgba(2, 5, 16, 0.6);
  backdrop-filter: blur(8px);
}
.entity-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(140, 170, 220, 0.9);
  letter-spacing: 0.05em;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.btn-rebuild, .btn-cancel, .btn-refresh {
  padding: 4px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  letter-spacing: 0.05em;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-rebuild {
  border: 1px solid rgba(124, 58, 237, 0.4);
  background: rgba(124, 58, 237, 0.25);
  color: #c4b5fd;
}
.btn-rebuild:hover:not(:disabled) {
  background: rgba(124, 58, 237, 0.45);
  color: #ddd6fe;
  border-color: rgba(167, 139, 250, 0.6);
  box-shadow: 0 0 10px rgba(124, 58, 237, 0.3);
}
.btn-rebuild:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-rebuild.running {
  background: rgba(124, 58, 237, 0.15);
  color: rgba(196, 181, 253, 0.7);
  border-color: rgba(124, 58, 237, 0.3);
}
.btn-cancel {
  border: 1px solid rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.15);
  color: #fca5a5;
}
.btn-cancel:hover {
  background: rgba(239, 68, 68, 0.3);
  color: #fecaca;
  border-color: rgba(239, 68, 68, 0.55);
}
.btn-refresh {
  border: 1px solid rgba(100, 140, 220, 0.25);
  background: rgba(30, 50, 100, 0.3);
  color: rgba(140, 170, 220, 0.8);
}
.btn-refresh:hover {
  background: rgba(60, 90, 180, 0.35);
  color: #c8d8f0;
  border-color: rgba(100, 160, 255, 0.45);
  box-shadow: 0 0 10px rgba(80, 130, 255, 0.2);
}
.btn-refresh:disabled { opacity: 0.4; cursor: not-allowed; }

.dot-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #a78bfa;
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.3); }
}

.entity-content {
  flex: 1;
  padding: 20px 16px;
  overflow: auto;
}

/* 进度卡片 */
.rebuild-card {
  background: #1a1d27;
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 16px;
  position: relative;
}
.rebuild-card.completed { border-color: rgba(34, 197, 94, 0.4); }
.rebuild-card.failed { border-color: rgba(239, 68, 68, 0.4); }
.rebuild-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #c4b5fd;
  margin-bottom: 12px;
}
.rebuild-card.completed .rebuild-header { color: #86efac; }
.rebuild-card.failed .rebuild-header { color: #fca5a5; }
.rebuild-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.running { background: #a78bfa; box-shadow: 0 0 6px rgba(167, 139, 250, 0.6); animation: pulse 1.2s ease-in-out infinite; }
.status-dot.done { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.6); }
.status-dot.failed { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.6); }
.rebuild-phase {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.7);
  padding: 2px 8px;
  background: rgba(124, 58, 237, 0.12);
  border-radius: 4px;
}
.rebuild-elapsed {
  margin-left: auto;
  font-size: 11px;
  color: #64748b;
  font-family: monospace;
}
.progress-bar {
  width: 100%;
  height: 8px;
  background: rgba(124, 58, 237, 0.12);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #7c3aed 0%, #a78bfa 100%);
  border-radius: 4px;
  transition: width 0.4s ease;
  box-shadow: 0 0 8px rgba(167, 139, 250, 0.5);
}
.rebuild-card.completed .progress-fill {
  background: linear-gradient(90deg, #16a34a 0%, #22c55e 100%);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
}
.progress-text {
  text-align: right;
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
  font-family: monospace;
}
.rebuild-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px 16px;
  margin-top: 12px;
  font-size: 12px;
}
.rs-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.rs-item-wide { grid-column: span 2; }
.rs-label { color: #64748b; }
.rs-val { color: #cbd5e1; font-family: monospace; font-weight: 600; }
.rs-val.success { color: #86efac; }
.rs-val.warn { color: #fcd34d; }
.rs-val.fail { color: #fca5a5; }
.rs-val.accent { color: #c4b5fd; }
.rs-sub { color: #475569; font-weight: 400; }
.rebuild-error {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 6px;
  font-size: 12px;
  color: #fca5a5;
  word-break: break-all;
}
.rebuild-log-toggle {
  margin-top: 10px;
  text-align: right;
}
.btn-link {
  background: none;
  border: none;
  color: #a78bfa;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.btn-link:hover { color: #c4b5fd; text-decoration: underline; }
.rebuild-log {
  margin-top: 8px;
  max-height: 240px;
  overflow: auto;
  background: #0f1117;
  border: 1px solid rgba(100, 120, 200, 0.15);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 11px;
  line-height: 1.5;
}
.log-line {
  color: #94a3b8;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-empty { color: #475569; font-style: italic; }

.entity-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: rgba(100, 130, 180, 0.5);
  font-size: 13px;
  letter-spacing: 0.1em;
}
.stat-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: #1a1d27;
  border-radius: 10px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #a78bfa;
  line-height: 1;
}
.stat-label {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 4px;
}
.stat-sub {
  font-size: 10px;
  color: #475569;
  font-family: monospace;
}
.graph-status-card {
  background: #1a1d27;
  border-radius: 10px;
  padding: 16px 20px;
}
.status-header {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
}
.status-body {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.status-dot.loaded {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
}
.status-text {
  font-size: 13px;
  color: #94a3b8;
}
.status-divider {
  color: #2d3149;
}
.status-info {
  font-size: 12px;
  color: #64748b;
}
</style>
