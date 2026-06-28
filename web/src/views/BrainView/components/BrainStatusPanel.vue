<script setup lang="ts">
/* 生命状态概览：scheduler / life_loop_status / activity / focus / energy / idle / mood / config / last_error
 * 数据来自 /brain/state（vm.state）。纯只读展示。 */
import { computed } from 'vue'
import { brainViewModel as vm } from '../BrainViewModel'

const life = vm.life
const config = vm.config

// scheduler + life_loop_status → 一个主状态徽标
const statusBadge = computed(() => {
  if (vm.hasStateError.value) return { text: '状态读取失败', cls: 'badge-err' }
  const running = vm.schedulerRunning.value
  const s = life.value?.life_loop_status || ''
  if (s.includes('error')) return { text: s || 'error', cls: 'badge-err' }
  if (running) return { text: s ? `运行中 · ${s}` : '运行中', cls: 'badge-run' }
  return { text: s ? `空闲 · ${s}` : '空闲', cls: 'badge-idle' }
})

const configSwitches = computed(() => {
  const c = config.value
  if (!c) return []
  return [
    { label: 'Session', on: !!c.brain_session_enabled },
    { label: 'LifeLoop', on: !!c.life_loop_enabled },
    { label: 'Proactive', on: !!c.proactive_contact_enabled },
  ]
})

const energyPct = computed(() => {
  const e = Number(life.value?.energy ?? 0)
  return `${Math.round(Math.max(0, Math.min(1, e)) * 100)}%`
})
</script>

<template>
  <section class="panel status-panel" data-testid="brain-status-panel">
    <div class="panel-head">
      <span class="panel-title">生命状态</span>
      <span v-if="vm.loadingState.value" class="badge badge-loading">刷新中</span>
      <span class="badge" :class="statusBadge.cls" data-testid="brain-scheduler-status">{{ statusBadge.text }}</span>
    </div>

    <!-- 错误态 -->
    <div v-if="vm.hasStateError.value" class="err-row" :data-testid="vm.errorState.value ? 'brain-state-error' : ''">
      后端状态读取失败{{ vm.state.value?.error ? `：${vm.state.value.error}` : '' }}，可点右上角刷新重试。
      <div v-if="vm.errorState.value" class="err-detail">{{ vm.errorState.value }}</div>
    </div>

    <template v-else-if="life">
      <div class="status-grid">
        <div class="kv">
          <span class="k">当前活动</span>
          <span class="v" data-testid="brain-current-activity">{{ life.current_activity || '--' }}</span>
        </div>
        <div class="kv">
          <span class="k">关注焦点</span>
          <span class="v focus" :title="life.current_focus || ''" data-testid="brain-current-focus">
            {{ life.current_focus || '--' }}
          </span>
        </div>
        <div class="kv">
          <span class="k">空闲时长</span>
          <span class="v" data-testid="brain-idle">{{ vm.formatSeconds(life.idle_seconds) }}</span>
        </div>
        <div class="kv">
          <span class="k">自主等级</span>
          <span class="v">{{ life.autonomy_level || config?.autonomy_level || '--' }}</span>
        </div>
      </div>

      <div class="energy-row">
        <span class="k">能量</span>
        <div class="bar"><div class="fill" :style="{ width: energyPct }" data-testid="brain-energy"></div></div>
        <span class="pct">{{ energyPct }}</span>
      </div>

      <div class="meta-row">
        <span class="meta"><span class="k">心情</span>{{ life.mood?.label || vm.formatScore(life.mood?.valence) }}</span>
        <span class="meta" v-if="life.next_wake_hint && Object.keys(life.next_wake_hint).length">
          <span class="k">下次唤醒</span>{{ life.next_wake_hint.tick_type || life.next_wake_hint.reason || '--' }}
        </span>
      </div>

      <!-- 配置开关（只展示） -->
      <div class="switch-row">
        <span v-for="sw in configSwitches" :key="sw.label" class="switch" :class="{ on: sw.on }" data-testid="brain-config-switch">
          <span class="dot"></span>{{ sw.label }}{{ sw.on ? ' 开' : ' 关' }}
        </span>
      </div>

      <!-- open_loops / goals 计数 -->
      <div class="count-row">
        <span class="cnt"><b>{{ life.open_loops?.length || 0 }}</b> 待办闭环</span>
        <span class="cnt"><b>{{ life.goals?.length || 0 }}</b> 目标</span>
        <span class="cnt"><b>{{ life.working_set?.length || 0 }}</b> 工作集</span>
      </div>

      <!-- 记忆整理信息 -->
      <div class="consolidation-row" data-testid="brain-consolidation-info">
        <span class="cons-label">记忆整理</span>
        <span class="cons-value">{{ vm.nextConsolidationLabel() }}</span>
        <span class="cons-sep">·</span>
        <span class="cons-label">待处理</span>
        <span class="cons-value">{{ vm.consolidationState.value?.pending_backlog ?? '--' }} 条</span>
        <span v-if="vm.consolidationState.value?.last_saved_at" class="cons-sep">·</span>
        <span v-if="vm.consolidationState.value?.last_saved_at" class="cons-label">上次</span>
        <span v-if="vm.consolidationState.value?.last_saved_at" class="cons-value">{{ vm.formatTime(vm.consolidationState.value?.last_saved_at) }}</span>
        <span v-if="vm.errorConsolidation.value" class="cons-err">{{ vm.errorConsolidation.value }}</span>
      </div>

      <!-- 错误栏（life.last_error） -->
      <div v-if="life.last_error" class="err-row soft" data-testid="brain-last-error">
        最近错误：{{ life.last_error }}
      </div>
    </template>

    <div v-else class="placeholder">等待状态数据…</div>
  </section>
</template>

<style scoped>
.panel { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.panel-head { display: flex; align-items: center; gap: 8px; }
.panel-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid transparent; }
.badge-run { background: #22c55e22; color: #86efac; border-color: #22c55e44; }
.badge-idle { background: #64748b22; color: #94a3b8; border-color: #64748b44; }
.badge-err { background: #ef444422; color: #fca5a5; border-color: #ef444444; }
.badge-loading { background: #eab30822; color: #fde68a; border-color: #eab30844; }

.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.kv { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.k { font-size: 10px; color: #64748b; }
.v { font-size: 13px; color: #e2e8f0; word-break: break-word; }
.v.focus { color: #a78bfa; }

.energy-row { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.energy-row .k { color: #64748b; min-width: 32px; }
.bar { flex: 1; height: 8px; background: #2d3149; border-radius: 4px; overflow: hidden; }
.fill { height: 100%; background: linear-gradient(90deg, #7c3aed, #a78bfa); border-radius: 4px; transition: width .3s; }
.pct { color: #a78bfa; font-weight: 600; min-width: 34px; text-align: right; }

.meta-row { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 11px; color: #cbd5e1; }
.meta .k { color: #64748b; margin-right: 4px; }

.switch-row { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 4px; border-top: 1px solid #2d3149; }
.switch { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: #64748b; padding: 3px 8px; border-radius: 4px; border: 1px solid #2d3149; }
.switch .dot { width: 6px; height: 6px; border-radius: 50%; background: #64748b; }
.switch.on { color: #86efac; border-color: #22c55e44; }
.switch.on .dot { background: #22c55e; }

.count-row { display: flex; gap: 16px; font-size: 11px; color: #64748b; }
.count-row .cnt b { color: #cbd5e1; font-weight: 600; }

.consolidation-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; font-size: 11px; color: #94a3b8; padding-top: 6px; border-top: 1px solid #2d3149; }
.cons-label { color: #64748b; }
.cons-value { color: #a78bfa; font-weight: 600; }
.cons-sep { color: #3b3f54; }
.cons-err { color: #fca5a5; font-size: 10px; }

.err-row { font-size: 12px; color: #fca5a5; background: #ef444414; border: 1px solid #ef444433; border-radius: 6px; padding: 8px 10px; }
.err-row.soft { color: #fde68a; background: #eab30814; border-color: #eab30833; }
.err-detail { font-size: 10px; color: #94a3b8; margin-top: 4px; word-break: break-word; }
.placeholder { font-size: 12px; color: #64748b; padding: 12px 0; text-align: center; }
</style>
