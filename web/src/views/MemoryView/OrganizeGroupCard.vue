<script setup lang="ts">
import { OrganizeGroupItem } from '../types'

const props = defineProps<{
  group: OrganizeGroupItem
}>()

const emit = defineEmits<{
  refine: [groupId: number]
  apply: [groupId: number]
}>()

function onRefineClick() {
  emit('refine', props.group.groupId)
}
function onApplyClick() {
  emit('apply', props.group.groupId)
}
</script>

<template>
  <div class="organize-group-card" :class="{ 'og-applied': group.isApplied }">
    <div class="og-label">
      组 {{ group.groupId + 1 }} · 相似度 {{ group.similarity }} · {{ group.memories.length }} 条
      <button v-if="group.isApplied" class="btn-secondary-sm og-refine-btn btn-applied" disabled>已合并</button>
      <button v-else-if="group.isRefining" class="btn-secondary-sm og-refine-btn btn-loading" disabled><span class="spin-icon">↻</span>提炼中</button>
      <button v-else-if="group.refineError" class="btn-secondary-sm og-refine-btn btn-error" @click="onRefineClick">{{ group.refineError }}</button>
      <button v-else-if="group.isRefined" class="btn-secondary-sm og-refine-btn" :disabled="group.isApplying" @click="onRefineClick">重新精炼</button>
      <button v-else class="btn-secondary-sm og-refine-btn" @click="onRefineClick">合并记忆</button>
    </div>
    <div v-for="(m, mi) in group.memories" :key="mi" class="og-item">
      <span class="og-idx">{{ mi + 1 }}</span>
      {{ m.text }}
    </div>

    <!-- Refined result -->
    <template v-if="group.isRefined && group.refinedText">
      <div class="og-refine-divider"></div>
      <div class="og-refine-label refined">合并结果</div>
      <div class="organize-refined-text" contenteditable="true">{{ group.refinedText }}</div>
      <div class="organize-category">分类: {{ group.category }}</div>
      <div class="og-refine-actions">
        <button v-if="group.isApplying" class="btn btn-sm btn-primary btn-loading" disabled><span class="spin-icon">↻</span>合并中</button>
        <button v-else-if="group.isApplied" class="btn btn-sm btn-primary btn-applied" disabled>已合并</button>
        <button v-else class="btn btn-sm btn-primary" @click="onApplyClick">确认合并</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.organize-group-card {
  background: #1e2235;
  border: 1px solid #2d3149;
  border-radius: 8px;
  padding: 12px;
}
.organize-group-card.og-applied {
  opacity: 0.5;
  border-color: #22c55e44;
}
.og-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 10px;
}
.og-item {
  display: flex;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #2d314944;
  font-size: 13px;
  color: #e2e8f0;
}
.og-item:last-child { border-bottom: none; }
.og-idx {
  width: 18px;
  height: 18px;
  background: #7c3aed33;
  color: #a78bfa;
  border-radius: 4px;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.btn-secondary-sm {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  border: 1px solid #7c3aed44;
  background: #7c3aed22;
  color: #a78bfa;
  cursor: pointer;
  transition: all .2s;
}
.btn-secondary-sm:hover:not(:disabled) { background: #7c3aed44; color: #c4b5fd; }
.btn-applied { background: #22c55e22; color: #22c55e; border-color: #22c55e44; cursor: default; }
.btn-loading { background: #7c3aed33; color: #c4b5fd; border-color: #7c3aed66; animation: btn-loading-pulse 2s ease-in-out infinite; }
@keyframes btn-loading-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px #7c3aed44; }
  50% { opacity: 0.7; box-shadow: none; }
}
.btn-refined { background: #22c55e22; color: #86efac; border-color: #22c55e44; }
.btn-error { background: #ef444422; color: #fca5a5; border-color: #ef444444; }
.btn-error:hover { background: #ef444444; color: #fecaca; }
.spin-icon { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.og-refine-divider { height: 1px; background: #2d3149; margin: 10px 0; }
.og-refine-label { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.og-refine-label.refined { color: #22c55e; }
.organize-refined-text {
  background: #141720;
  border: 1px solid #2d3149;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  color: #e2e8f0;
  min-height: 40px;
  outline: none;
}
.organize-refined-text:focus { border-color: #7c3aed; }
.organize-category { font-size: 11px; color: #64748b; margin-top: 6px; }
.og-refine-actions { margin-top: 10px; }
.btn-sm { padding: 4px 12px; font-size: 12px; border-radius: 4px; border: none; cursor: pointer; transition: all .2s; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #6d28d9; }
.btn-primary.btn-loading { background: #7c3aed88; cursor: not-allowed; }
.btn-primary.btn-applied { background: #22c55e66; cursor: default; }
</style>
