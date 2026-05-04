<script setup lang="ts">
import { overviewViewModel } from '../index'

const qdrantCard = overviewViewModel.qdrantCard
</script>

<template>
  <div class="status-card">
    <div class="sc-label-row">
      <div class="sc-label">Qdrant 状态</div>
      <span :class="qdrantCard.badgeClass()">
        <span v-if="qdrantCard.badge.value === 'loading'" class="mini-loading sm"></span>
        <template v-else>{{ qdrantCard.badge.value === 'ok' ? 'OK' : qdrantCard.badge.value }}</template>
      </span>
    </div>
    <div class="sc-sub">{{ qdrantCard.detail.value || '向量数据库' }}</div>
  </div>
</template>

<style scoped>
.status-card { flex: 1; min-width: 160px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; }
.sc-label-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.sc-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.sc-sub { font-size: 11px; color: #64748b; margin-top: 2px; }
.mini-loading { display: inline-block; width: 12px; height: 12px; border: 2px solid #eab30844; border-top-color: #fde047; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.badge-ok { display: inline-flex; align-items: center; padding: 2px 8px; background: #22c55e22; color: #86efac; border: 1px solid #22c55e44; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge-err { display: inline-flex; align-items: center; padding: 2px 8px; background: #ef444422; color: #fca5a5; border: 1px solid #ef444444; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge-loading { display: inline-flex; align-items: center; padding: 2px 8px; background: #eab30822; color: #fde68a; border: 1px solid #eab30844; border-radius: 4px; font-size: 10px; font-weight: 600; }
</style>
