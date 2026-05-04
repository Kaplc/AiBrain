<script setup lang="ts">
import { overviewViewModel } from '../index'

const flaskCard = overviewViewModel.flaskCard
</script>

<template>
  <div class="status-card">
    <div class="sc-label-row">
      <div class="sc-label">Flask 状态</div>
      <div class="sc-label-row-btns">
        <button
          class="flask-restart-btn"
          :disabled="flaskCard.restarting.value"
          @click="flaskCard.restart()"
        >{{ flaskCard.restarting.value ? '重启中...' : '重启' }}</button>
        <span :class="flaskCard.badgeClass()">{{ flaskCard.badge.value === 'ok' ? 'OK' : flaskCard.badge.value }}</span>
      </div>
    </div>
    <div class="sc-sub">{{ overviewViewModel.formatUptime(flaskCard.uptime.value) }}</div>
    <div class="sc-sub" v-if="flaskCard.detail.value">{{ flaskCard.detail.value }}</div>
  </div>
</template>

<style scoped>
.status-card { flex: 1; min-width: 160px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; }
.sc-label-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.sc-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.sc-sub { font-size: 11px; color: #64748b; margin-top: 2px; }
.badge-ok { display: inline-flex; align-items: center; padding: 2px 8px; background: #22c55e22; color: #86efac; border: 1px solid #22c55e44; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge-err { display: inline-flex; align-items: center; padding: 2px 8px; background: #ef444422; color: #fca5a5; border: 1px solid #ef444444; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge-loading { display: inline-flex; align-items: center; padding: 2px 8px; background: #eab30822; color: #fde68a; border: 1px solid #eab30844; border-radius: 4px; font-size: 10px; font-weight: 600; }
.sc-label-row-btns { display: flex; align-items: center; gap: 6px; }
.flask-restart-btn { padding: 2px 8px; border: 1px solid #2d3149; border-radius: 4px; font-size: 10px; color: #64748b; background: transparent; cursor: pointer; }
.flask-restart-btn:hover { border-color: #ef4444; color: #ef4444; }
.flask-restart-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
