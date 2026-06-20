<script setup lang="ts">
/* Pending 表达队列：当前「想说但还没说」的意图。数据来自 /brain/state.life_state.pending_expressions。
 * 字段：source / source_node_id / expression_score / note / created_at。纯只读。 */
import { brainViewModel as vm } from '../BrainViewModel'
</script>

<template>
  <section class="panel pending-panel" data-testid="brain-pending-panel">
    <div class="panel-head">
      <span class="panel-title">待表达意图</span>
      <span class="count" data-testid="brain-pending-count">{{ vm.pendings.value.length }}</span>
    </div>

    <div v-if="!vm.pendings.value.length" class="placeholder">队列空：没有想主动表达的内容</div>

    <div v-else class="pend-items">
      <div v-for="(p, i) in vm.pendings.value" :key="p.id || i" class="pend-item" data-testid="brain-pending-item">
        <div class="pi-top">
          <span class="src">{{ p.source || p.type || '--' }}</span>
          <span class="score" data-testid="brain-pending-score">价值 {{ vm.formatScore(p.expression_score) }}</span>
        </div>
        <div class="pi-node" v-if="p.source_node_id" :title="p.source_node_id">{{ p.source_node_id }}</div>
        <div class="pi-note" v-if="p.note">{{ p.note }}</div>
        <div class="pi-foot">
          <span>{{ vm.formatTime(p.created_at) }}</span>
          <span class="state">{{ p.expressed ? '已表达' : '待发送' }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.panel-head { display: flex; align-items: center; gap: 8px; }
.panel-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.count { font-size: 10px; color: #a78bfa; background: #7c3aed1a; border: 1px solid #7c3aed44; padding: 1px 7px; border-radius: 8px; font-weight: 600; }
.placeholder { font-size: 12px; color: #64748b; padding: 14px 0; text-align: center; }

.pend-items { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; max-height: 240px; }
.pend-item { background: #14161f; border: 1px solid #2d3149; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 3px; }
.pi-top { display: flex; align-items: center; justify-content: space-between; }
.src { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #c4b5fd; background: #a78bfa1a; padding: 1px 6px; border-radius: 3px; }
.score { font-size: 10px; color: #fbbf24; }
.pi-node { font-size: 11px; color: #cbd5e1; word-break: break-word; font-family: ui-monospace, monospace; }
.pi-note { font-size: 11px; color: #94a3b8; }
.pi-foot { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: #64748b; }
.pi-foot .state { color: #fde68a; }
</style>
