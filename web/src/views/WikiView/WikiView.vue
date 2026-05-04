<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { wikiViewModel } from './WikiViewModel'
import FileList from './FileList/FileList.vue'
import SideStats from './SideStats/SideStats.vue'
import SideOps from './SideOps/SideOps.vue'
import SideSettings from './SideSettings/SideSettings.vue'

onMounted(() => wikiViewModel.onMounted())
onUnmounted(() => wikiViewModel.onUnmounted())
</script>

<template>
  <div class="wiki-wrap">
    <Transition name="toast-fade">
      <div v-if="wikiViewModel.copyToastVisible.value" class="copy-toast">路径已复制</div>
    </Transition>

    <div class="wiki-header">
      <div class="wiki-title">Wiki 知识库</div>
    </div>

    <div class="wiki-body">
      <div class="wiki-main">
        <FileList />
      </div>

      <div class="wiki-sidebar">
        <div class="side-tab-bar">
          <button
            class="side-tab-btn"
            :class="{ active: wikiViewModel.activeTab.value === 'stats' }"
            @click="wikiViewModel.switchTab('stats')"
          >统计</button>
          <button
            class="side-tab-btn"
            :class="{ active: wikiViewModel.activeTab.value === 'ops' }"
            @click="wikiViewModel.switchTab('ops')"
          >操作</button>
          <button
            class="side-tab-btn"
            :class="{ active: wikiViewModel.activeTab.value === 'settings' }"
            @click="wikiViewModel.switchTab('settings')"
          >设置</button>
        </div>

        <div class="side-content">
          <SideStats v-show="wikiViewModel.activeTab.value === 'stats'" />
          <SideOps v-show="wikiViewModel.activeTab.value === 'ops'" />
          <SideSettings v-show="wikiViewModel.activeTab.value === 'settings'" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* === Layout === */
.wiki-wrap {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-sizing: border-box;
  height: 100%;
  overflow: hidden;
}
.wiki-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.wiki-title {
  font-size: 18px;
  font-weight: 700;
}

/* Two-column body */
.wiki-body {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.wiki-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* === Right Sidebar === */
.wiki-sidebar {
  width: 300px;
  min-width: 260px;
  flex-shrink: 0;
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.side-tab-bar {
  display: flex;
  background: #12141c;
  border-bottom: 1px solid #2d3149;
  padding: 4px;
  flex-shrink: 0;
}
.side-tab-btn {
  flex: 1;
  padding: 7px 0;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all .15s;
  user-select: none;
  border: none;
  background: transparent;
  color: #64748b;
  text-align: center;
}
.side-tab-btn:hover {
  color: #94a3b8;
}
.side-tab-btn.active {
  background: #7c3aed33;
  color: #a78bfa;
}

.side-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.side-panel {
  display: none;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 14px;
}
.side-panel.active {
  display: flex;
}

/* === Stats Cards === */
.wscard-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wscard {
  background: #12141c;
  border: 1px solid #2d3149;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wsc-label {
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 600;
}
.wsc-value {
  font-size: 22px;
  font-weight: 700;
  color: #e2e8f0;
}
.wsc-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

/* === Ops Panel === */
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

/* === Index Result === */
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

/* === File Table === */
.file-section {
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
.fs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.fs-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.table-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.file-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #12141c;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid #2d3149;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}
.file-table th:hover {
  color: #94a3b8;
}
.file-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1a1d27;
  vertical-align: top;
}
.file-table tbody tr:hover {
  background: #12141c;
}
.ft-name {
  color: #a78bfa;
  font-weight: 500;
  white-space: nowrap;
}
.ft-meta {
  color: #64748b;
  white-space: nowrap;
  font-size: 12px;
}
.ft-preview {
  color: #94a3b8;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

/* === Settings Panel === */
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

/* === Form Elements === */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
}
.form-input,
.form-select {
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid #2d3149;
  background: #12141c;
  color: #e2e8f0;
  font-size: 13px;
  outline: none;
  transition: border-color .2s;
}
.form-input:focus,
.form-select:focus {
  border-color: #7c3aed;
}

/* === Buttons === */
.btn-save {
  padding: 8px 24px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s;
  border: none;
  user-select: none;
  background: #7c3aed33;
  color: #a78bfa;
  border: 1px solid #7c3aed44;
}
.btn-save:hover {
  background: #7c3aed55;
}
.btn-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* === Misc === */
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
  to { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  color: #64748b;
  padding: 40px 20px;
  font-size: 13px;
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

.toast-fade-enter-active {
  animation: toastIn 0.2s ease;
}
.toast-fade-leave-active {
  animation: toastOut 1s ease forwards;
}
@keyframes toastIn {
  from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
  to   { opacity: 1; transform: translateX(-50%); }
}
@keyframes toastOut {
  0%   { opacity: 1; transform: translateX(-50%); }
  100% { opacity: 0; transform: translateX(-50%) translateY(12px); }
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
  background-image: linear-gradient(
    90deg,
    rgba(255,255,255,0) 0%,
    rgba(255,255,255,.2) 50%,
    rgba(255,255,255,0) 100%
  );
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