<script setup lang="ts">
import { onMounted } from 'vue'
import { logsViewModel } from './LogsViewModel'

onMounted(() => {
  console.log('[logs] onPageLoad start')
  logsViewModel.loadLog()
  console.log('[logs] onPageLoad done')
})
</script>

<template>
  <div class="logs-wrap">
    <div class="logs-title">日志</div>
    <div class="log-section">
      <div class="log-header">
        <div class="log-title-text">系统日志</div>
        <span class="ft-meta">{{ logsViewModel.meta.value }}</span>
        <button
          class="btn-action btn-secondary"
          style="padding: 4px 12px; font-size: 11px"
          @click="logsViewModel.loadLog()"
        >
          刷新
        </button>
      </div>
      <div class="log-wrap" ref="logsViewModel.logWrapEl.value">
        <div v-if="logsViewModel.loading.value" class="mini-loading"></div>
        <div v-else-if="logsViewModel.error.value" class="empty-state">{{ logsViewModel.error.value }}</div>
        <div v-else-if="logsViewModel.logLines.value.length === 0" class="empty-state">
          点击「刷新」加载日志
        </div>
        <template v-else>
          <div
            v-for="(line, i) in logsViewModel.logLines.value"
            :key="i"
            class="log-line"
            :class="line.cls"
            title="点击复制"
            @click="logsViewModel.copyLine(line.raw)"
            v-html="line.html"
          />
        </template>
      </div>
    </div>
    <Transition name="toast">
      <div v-if="logsViewModel.copyToastVisible.value" class="copy-toast">已复制</div>
    </Transition>
  </div>
</template>

<style scoped>
.logs-wrap {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-sizing: border-box;
  height: 100%;
  overflow: hidden;
}

.logs-title {
  font-size: 18px;
  font-weight: 700;
}

.log-section {
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.log-title-text {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}

.log-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.6;
  font-family: 'Consolas', monospace;
}

.log-line {
  color: #94a3b8;
  white-space: pre-wrap;
  word-break: break-all;
  border-bottom: 1px solid #12141c;
  padding: 2px 4px;
  cursor: pointer;
}

.log-line:hover {
  background: #12141c;
}

.log-time {
  color: #64748b;
}

.log-level-info {
  color: #86efac;
}

.log-level-warn {
  color: #fde047;
}

.log-level-error {
  color: #fca5a5;
}

.mini-loading {
  display: block;
  width: 24px;
  height: 24px;
  border: 2px solid #eab30844;
  border-top-color: #fde047;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 24px auto;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-state {
  text-align: center;
  color: #64748b;
  padding: 40px 20px;
  font-size: 13px;
}

.btn-action {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  user-select: none;
}

.btn-secondary {
  background: #1e293b;
  color: #94a3b8;
  border: 1px solid #2d3149;
}

.btn-secondary:hover {
  background: #263044;
  color: #cbd5e1;
}

.ft-meta {
  color: #64748b;
  white-space: nowrap;
  font-size: 12px;
}

.copy-toast {
  position: fixed;
  top: 36px;
  left: 50%;
  transform: translateX(-50%);
  background: #22c55e22;
  color: #86efac;
  border: 1px solid #22c55e44;
  font-size: 11px;
  padding: 4px 16px;
  border-radius: 6px;
  pointer-events: none;
  z-index: 100;
}

.toast-enter-active {
  animation: fadeIn 0.2s ease;
}

.toast-leave-active {
  animation: fadeOut 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-12px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

@keyframes fadeOut {
  from {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  to {
    opacity: 0;
    transform: translateX(-50%) translateY(12px);
  }
}
</style>
