<script setup lang="ts">
import { overviewViewModel } from '../index'

const deviceCard = overviewViewModel.deviceCard
</script>

<template>
  <div class="status-card">
    <div class="sc-label-row">
      <div class="sc-label">设备信息</div>
    </div>
    <div class="sc-sub">CPU: {{ deviceCard.info.value?.cpu_percent || '--' }}%</div>
    <div class="sc-sub">内存: {{ deviceCard.info.value?.memory_percent || '--' }}%</div>
    <div class="sc-sub">设备: {{ deviceCard.info.value?.gpu_name ? 'GPU' : 'CPU' }}</div>
    <div v-if="deviceCard.info.value?.gpu_name" class="sc-sub">{{ deviceCard.info.value.gpu_name }}</div>
  </div>
</template>

<style scoped>
.status-card { flex: 1; min-width: 160px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; }
.sc-label-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.sc-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.sc-sub { font-size: 11px; color: #64748b; margin-top: 2px; }
</style>
