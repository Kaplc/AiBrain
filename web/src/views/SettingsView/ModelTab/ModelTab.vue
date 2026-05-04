<script setup lang="ts">
import { settingsViewModel } from '../index'

const modelTab = settingsViewModel.modelTab
</script>

<template>
  <div class="tab-content">
    <div class="set-row">
      <div class="set-row-label">
        <div class="set-label">模型</div>
        <div class="set-desc">{{ modelTab.desc.value }}</div>
      </div>
      <select class="model-select" disabled>
        <option value="BAAI/bge-m3">BAAI/bge-m3</option>
      </select>
    </div>

    <div class="set-row">
      <div class="set-row-label">
        <div class="set-label">推理设备</div>
        <div class="set-desc">选择模型推理使用的硬件</div>
      </div>
      <select class="device-select" v-model="modelTab.pendingDevice.value">
        <option value="auto">自动</option>
        <option value="gpu">GPU</option>
        <option value="cpu">CPU</option>
      </select>
    </div>

    <div class="gpu-info" :class="modelTab.gpuInfoClass.value" v-html="modelTab.gpuInfoHtml.value"></div>

    <div class="header-actions">
      <button class="btn btn-secondary" @click="modelTab.reset()">重置</button>
      <button class="btn btn-primary" :disabled="modelTab.saving.value" @click="modelTab.apply()">
        {{ modelTab.saving.value ? '保存中...' : '保存' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tab-content { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.set-row { display: flex; align-items: center; gap: 16px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; }
.set-row-label { flex: 1; min-width: 0; }
.set-label { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.set-desc { font-size: 11px; color: #64748b; margin-top: 2px; }
.gpu-info { background: #0f1117; border: 1px solid #2d3149; border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #64748b; }
.gpu-info.ok { color: #86efac; border-color: #22c55e44; }
.gpu-info.warn { color: #fde68a; border-color: #f59e0b44; }
.gpu-info.err { color: #fca5a5; border-color: #ef444444; }
.gpu-info :deep(code) { background: #1e293b; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11px; white-space: nowrap; }
.model-select, .device-select { background: #0f1117; border: 1px solid #2d3149; border-radius: 8px; color: #e2e8f0; padding: 8px 12px; font-size: 13px; font-family: inherit; outline: none; cursor: pointer; min-width: 140px; }
.model-select:focus, .device-select:focus { border-color: #7c3aed; }
.header-actions { display: flex; gap: 8px; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity .2s; }
.btn:active { transform: scale(.98); }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover { opacity: .85; }
.btn-primary:disabled { opacity: .4; cursor: not-allowed; }
.btn-secondary { background: #1e293b; color: #94a3b8; border: 1px solid #2d3149; }
.btn-secondary:hover { border-color: #475569; }
</style>
