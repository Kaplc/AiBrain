<script setup lang="ts">
import { memoryViewModel } from './index'
import OrganizeGroupCard from './OrganizeGroupCard.vue'

const vm = memoryViewModel
</script>

<template>
  <div class="tab-panel">
    <div class="organize-toolbar">
      <select v-model="vm.organizeTab.threshold.value" class="organize-select" :disabled="vm.organizeTab.busy.value">
        <option value="0.90">严格去重</option>
        <option value="0.85">中等去重</option>
        <option value="0.80">宽松去重</option>
      </select>
      <button class="btn btn-accent" :disabled="vm.organizeTab.busy.value" @click="vm.organizeTab.start()">开始分析</button>
    </div>

    <div class="memory-list-container">
      <template v-if="vm.organizeTab.busy.value">
        <div v-if="vm.organizeTab.groups.value.length" class="organize-header">
          <span>已发现 {{ vm.organizeTab.groups.value.length }} 组...</span>
        </div>
        <div class="organize-groups">
          <OrganizeGroupCard
            v-for="(g, idx) in vm.organizeTab.groups.value"
            :key="g.groupId"
            :group="g"
            :class="{ 'new-group': idx === vm.organizeTab.groups.value.length - 1 && vm.organizeTab.busy.value }"
            @refine="(id) => vm.organizeTab.refineGroup(id)"
            @apply="(id) => vm.organizeTab.applySingle(id)"
          ></OrganizeGroupCard>
        </div>
        <div class="organize-loading">
          <div class="loading-spinner"></div>
          <div class="loading-text">正在分析记忆相似度...</div>
        </div>
      </template>
      <template v-else-if="vm.organizeTab.groups.value.length">
        <div class="organize-header">
          <span>共发现 {{ vm.organizeTab.groups.value.length }} 组相似</span>
        </div>
        <div class="organize-groups">
          <OrganizeGroupCard
            v-for="g in vm.organizeTab.groups.value"
            :key="g.groupId"
            :group="g"
            @refine="(id) => vm.organizeTab.refineGroup(id)"
            @apply="(id) => vm.organizeTab.applySingle(id)"
          ></OrganizeGroupCard>
        </div>
      </template>
      <div v-else class="empty">
        <div class="empty-icon">🧹</div>
        <div class="empty-text">点击"开始分析"扫描重复记忆</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.organize-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.organize-select { background: #1e2235; color: #e2e8f0; border: 1px solid #2d3149; border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer; }
.organize-select:focus { outline: none; border-color: #7c3aed; }
.btn { padding: 6px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.btn-accent { background: #7c3aed; color: #fff; }
.btn-accent:hover:not(:disabled) { background: #6d28d9; }
.btn-accent:disabled { background: #4a4a5a; color: #888; cursor: not-allowed; opacity: 0.6; }
.btn-warn { background: #f59e0b; color: #fff; }
.btn-warn:hover { background: #d97706; }
.btn-danger-sm { background: #ef4444; color: #fff; padding: 4px 12px; font-size: 12px; }
.btn-danger-sm:hover { background: #dc2626; }
.memory-list-container { flex: 1; overflow: auto; }
.organize-loading { text-align: center; padding: 40px; color: #94a3b8; font-size: 14px; }
.loading-spinner { width: 32px; height: 32px; border: 3px solid #2d3149; border-top-color: #7c3aed; border-radius: 50%; animation: spin .8s linear infinite; margin: 0 auto 16px; }
.loading-text { font-size: 14px; color: #94a3b8; }
.loading-progress { font-size: 12px; color: #64748b; margin-top: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }
.organize-header { padding: 8px 0 12px; font-size: 13px; color: #94a3b8; }
.organize-groups { display: flex; flex-direction: column; gap: 12px; }
.new-group { animation: group-appear 0.4s ease-out; }
@keyframes group-appear {
  from { opacity: 0; transform: translateY(-10px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; color: #64748b; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
