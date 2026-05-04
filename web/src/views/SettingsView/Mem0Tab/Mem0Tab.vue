<script setup lang="ts">
import { settingsViewModel } from '../index'

const mem0Tab = settingsViewModel.mem0Tab
</script>

<template>
  <div class="tab-content">
    <div class="config-form">
      <div v-if="!mem0Tab.form.fields.length" class="loading">加载中...</div>
      <template v-for="f in mem0Tab.form.fields" :key="f.key">
        <div v-if="f.type === 'dir'" class="form-row">
          <label>{{ f.label }}</label>
          <div class="dir-input-wrap">
            <input
              type="text"
              :value="mem0Tab.form.values[f.key]"
              @input="mem0Tab.form.values[f.key] = ($event.target as HTMLInputElement).value"
              @change="mem0Tab.onInput(f.key)"
              @blur="mem0Tab.onInput(f.key)"
              :placeholder="String(f.default ?? '')"
            />
            <button type="button" class="dir-browse-btn" @click="mem0Tab.browseDir(f.key)">&#128193;</button>
            <span class="dir-status" :class="mem0Tab.dirChecks['mem0_' + f.key] || ''">
              {{ mem0Tab.dirChecks['mem0_' + f.key] === 'ok' ? '✓' : mem0Tab.dirChecks['mem0_' + f.key] === 'err' ? '✗ 不存在' : '' }}
            </span>
          </div>
        </div>
        <div v-else class="form-row">
          <label>{{ f.label }}</label>
          <input
            :type="settingsViewModel.inputType(f.type)"
            :value="mem0Tab.form.values[f.key]"
            @input="mem0Tab.form.values[f.key] = ($event.target as HTMLInputElement).value"
            :placeholder="String(f.default ?? '')"
          />
        </div>
      </template>
    </div>
    <div class="header-actions">
      <button class="btn btn-secondary" @click="mem0Tab.reset()">恢复默认</button>
      <button class="btn btn-primary" @click="mem0Tab.save()">保存</button>
    </div>
  </div>
</template>

<style scoped>
.tab-content { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.config-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; align-items: center; gap: 12px; }
.form-row label { font-size: 12px; color: #94a3b8; min-width: 120px; }
.form-row input { flex: 1; background: #0f1117; border: 1px solid #2d3149; border-radius: 6px; color: #e2e8f0; padding: 6px 10px; font-size: 13px; font-family: inherit; outline: none; }
.form-row input:focus { border-color: #7c3aed; }
.loading { font-size: 12px; color: #64748b; text-align: center; padding: 20px; }
.dir-input-wrap { display: flex; align-items: center; flex: 1; gap: 8px; }
.dir-input-wrap input { flex: 1; }
.dir-browse-btn { padding: 6px 10px; background: #2d3149; border: 1px solid #2d3149; border-radius: 6px; cursor: pointer; font-size: 14px; color: #e2e8f0; }
.dir-browse-btn:hover { background: #7c3aed; border-color: #7c3aed; }
.dir-status { font-size: 12px; min-width: 60px; }
.dir-status.ok { color: #86efac; }
.dir-status.err { color: #fca5a5; }
.header-actions { display: flex; gap: 8px; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity .2s; }
.btn:active { transform: scale(.98); }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover { opacity: .85; }
.btn-secondary { background: #1e293b; color: #94a3b8; border: 1px solid #2d3149; }
.btn-secondary:hover { border-color: #475569; }
</style>
