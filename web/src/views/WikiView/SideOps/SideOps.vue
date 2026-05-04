<script setup lang="ts">
import { wikiViewModel } from '../WikiViewModel'
</script>

<template>
  <div class="side-panel active">
    <div class="ops-section">
      <div class="ops-title">快捷操作</div>
      <div class="ops-list">
        <button class="ops-btn" :disabled="wikiViewModel.showProgress.value" @click="wikiViewModel.rebuildIndex()">
          <span class="ops-icon">&#x21bb;</span>
          <span class="ops-text">{{ wikiViewModel.showProgress.value ? '索引中...' : '重建索引' }}</span>
        </button>
      </div>
      <div
        v-if="wikiViewModel.indexResultMsg.value"
        class="index-result"
        :class="wikiViewModel.indexResultMsg.value.type"
      >{{ wikiViewModel.indexResultMsg.value.text }}</div>
      <div v-if="wikiViewModel.showProgress.value" style="display:flex;flex-direction:column;flex:1;min-height:0;margin-top:8px">
        <div class="progress-label">{{ wikiViewModel.progressLabel.value }}</div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" :style="{ width: wikiViewModel.progressPct.value }"></div>
        </div>
        <div class="progress-pct">{{ wikiViewModel.progressPct.value }}</div>
        <div ref="wikiViewModel.logWrapEl.value" class="index-log-wrap" style="margin-top:8px">
          <div v-for="(line, i) in wikiViewModel.logLines.value" :key="i" class="log-line">{{ line }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.side-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 14px;
}
.side-panel.active {
  display: flex;
}
.ops-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ops-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.ops-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ops-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #12141c;
  border: 1px solid #2d3149;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
  user-select: none;
}
.ops-btn:hover {
  background: #1e293b;
  color: #e2e8f0;
  border-color: #7c3aed44;
}
.ops-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.ops-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}
.ops-text {
  white-space: nowrap;
}
.index-result {
  font-size: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  line-height: 1.6;
}
.index-result.ok {
  background: #22c55e11;
  color: #86efac;
  border: 1px solid #22c55e22;
}
.index-result.err {
  background: #ef444411;
  color: #fca5a5;
  border: 1px solid #ef444422;
}
.progress-label {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.progress-bar-bg {
  background: #0f1117;
  border: 1px solid #2d3149;
  border-radius: 4px;
  height: 20px;
  overflow: hidden;
  position: relative;
}
.progress-bar-fill {
  height: 100%;
  background-color: #7c3aed;
  background-image: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.2) 50%, rgba(255,255,255,0) 100%);
  border-radius: 4px;
  transition: width 0.4s ease;
  position: relative;
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
.progress-pct {
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
  text-align: right;
  margin-top: 4px;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.index-log-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #0f1117;
  border: 1px solid #2d3149;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: monospace;
  font-size: 10px;
  color: #94a3b8;
  line-height: 1.5;
  word-break: break-all;
}
.index-log-wrap .log-line {
  opacity: .7;
}
.index-log-wrap .log-line:last-child {
  opacity: 1;
  color: #e2e8f0;
}
</style>
