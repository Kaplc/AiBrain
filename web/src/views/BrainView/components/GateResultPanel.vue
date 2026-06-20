<script setup lang="ts">
/* Gate / 主动表达观察区。
 *
 * 说明：ExpressionGate 的 send/hold/suppress 判定在后台 tick 中实时计算，
 * 当前未持久化到 /brain/state 可读字段（plan FR-007 标记为 P1，需后续补充）。
 * 这里只读地展示：proactive 配置开关、冷却状态、以及当前选中 run 最近一轮的
 * notify_candidate（想主动联系时 judge 写入的候选）。无 gate 记录则优雅提示，不伪造。
 */
import { computed } from 'vue'
import { brainViewModel as vm } from '../BrainViewModel'
import type { BrainCycle } from '../types'

const proactiveOn = computed(() => !!vm.config.value?.proactive_contact_enabled)

const cooldownText = computed(() => {
  const last = vm.life.value?.last_proactive_contact_at
  if (!last) return '尚无主动联系记录'
  return `上次主动联系：${vm.formatTime(last)}`
})

// 选中 run 里最近一个带 notify_candidate 的 cycle
const lastNotify = computed(() => {
  const cycles = vm.selectedRun.value?.cycles
  if (!cycles?.length) return null
  for (let i = cycles.length - 1; i >= 0; i--) {
    const c: BrainCycle = cycles[i]
    const n = c.notify_candidate
    if (n && typeof n === 'object' && Object.keys(n).length) return { cycle: c, n }
  }
  return null
})
</script>

<template>
  <section class="panel gate-panel" data-testid="brain-gate-panel">
    <div class="panel-head">
      <span class="panel-title">主动表达 Gate</span>
      <span class="badge" :class="proactiveOn ? 'badge-on' : 'badge-off'" data-testid="brain-proactive-state">
        {{ proactiveOn ? '已开启' : '已关闭' }}
      </span>
    </div>

    <div class="gate-meta">
      <div class="meta-line"><span class="k">闸门开关</span>{{ proactiveOn ? 'proactive_contact 已开启，候选可经 gate 评估发送' : 'proactive_contact 关闭，所有候选 suppress' }}</div>
      <div class="meta-line"><span class="k">冷却状态</span>{{ cooldownText }}</div>
    </div>

    <div v-if="lastNotify" class="notify-box" data-testid="brain-notify-candidate">
      <div class="nb-title">最近一轮通知候选（来自 run #{{ lastNotify.cycle.cycle_index }}）</div>
      <div class="nb-topic" v-if="lastNotify.n.topic || lastNotify.n.source_node_id">
        {{ lastNotify.n.topic || lastNotify.n.source_node_id }}
      </div>
      <div class="nb-note" v-if="lastNotify.n.note || lastNotify.n.reason">{{ lastNotify.n.note || lastNotify.n.reason }}</div>
      <div class="nb-val" v-if="typeof lastNotify.n.value === 'number'">价值 {{ vm.formatScore(lastNotify.n.value) }}</div>
    </div>

    <div v-else class="placeholder">
      暂无主动表达 gate 记录。<br />
      <span class="hint">gate 在后台 life tick 中实时评估 send/hold/suppress，结果需后续持久化才能在此展示。</span>
    </div>
  </section>
</template>

<style scoped>
.panel { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.panel-head { display: flex; align-items: center; gap: 8px; }
.panel-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.badge-on { background: #22c55e22; color: #86efac; border: 1px solid #22c55e44; }
.badge-off { background: #64748b22; color: #94a3b8; border: 1px solid #64748b44; }

.gate-meta { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; background: #14161f; border: 1px solid #2d3149; border-radius: 6px; }
.meta-line { font-size: 11px; color: #94a3b8; word-break: break-word; }
.meta-line .k { color: #64748b; margin-right: 5px; font-size: 10px; }

.notify-box { background: #7c3aed10; border: 1px solid #7c3aed44; border-radius: 8px; padding: 9px 11px; display: flex; flex-direction: column; gap: 3px; }
.nb-title { font-size: 10px; color: #c4b5fd; }
.nb-topic { font-size: 12px; color: #e2e8f0; font-family: ui-monospace, monospace; word-break: break-word; }
.nb-note { font-size: 11px; color: #94a3b8; }
.nb-val { font-size: 10px; color: #fbbf24; }

.placeholder { font-size: 12px; color: #64748b; padding: 10px 0; text-align: center; line-height: 1.7; }
.hint { font-size: 10px; color: #475569; }
</style>
