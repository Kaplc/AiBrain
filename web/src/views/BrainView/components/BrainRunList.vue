<script setup lang="ts">
/* 最近 run 列表 + mode 过滤。数据来自 /brain/runs/recent（vm.runs）。
 * 点击 run → vm.selectRun(id) 触发按需加载详情。纯只读。 */
import { brainViewModel as vm } from '../BrainViewModel'
import type { ModeFilter } from '../types'

const filters: { key: ModeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'reactive', label: 'Reactive' },
  { key: 'background', label: 'Background' },
]

function modeCls(mode?: string): string {
  if (mode === 'reactive') return 'mode-reactive'
  if (mode === 'background') return 'mode-background'
  return 'mode-other'
}
</script>

<template>
  <section class="panel run-list" data-testid="brain-run-list">
    <div class="panel-head">
      <span class="panel-title">最近循环</span>
      <span class="count">共 {{ vm.runs.value.length }} 条</span>
      <div class="tab-group" data-testid="brain-mode-filter">
        <button v-for="f in filters" :key="f.key" class="tab" :class="{ active: vm.modeFilter.value === f.key }"
          @click="vm.setModeFilter(f.key)">{{ f.label }}</button>
      </div>
    </div>

    <div v-if="vm.loadingRuns.value && !vm.runs.value.length" class="placeholder">加载中…</div>

    <div v-else-if="vm.errorRuns.value" class="err-row" data-testid="brain-runs-error">
      列表读取失败：{{ vm.errorRuns.value }}
      <button class="retry" @click="vm.loadRecent()">重试</button>
    </div>

    <div v-else-if="!vm.runs.value.length" class="placeholder">暂无循环记录（系统空闲时后台 tick 会在此累积）</div>

    <div v-else class="run-items">
      <button v-for="r in vm.runs.value" :key="r.run_id" class="run-item"
        :class="{ selected: r.run_id === vm.selectedRunId.value }"
        :data-testid="`brain-run-item`" :data-run-id="r.run_id"
        @click="vm.selectRun(r.run_id)">
        <div class="ri-top">
          <span class="mode" :class="modeCls(r.mode)">{{ r.mode || '--' }}</span>
          <span class="rid" :title="r.run_id">{{ r.run_id }}</span>
        </div>
        <div class="ri-mid">
          <span class="chip" v-if="r.selected_activity">{{ r.selected_activity }}</span>
          <span class="chip ghost" v-if="r.cycle_count !== undefined">{{ r.cycle_count }} cycles</span>
          <span class="chip" :class="`stop-${(r.stop_reason || 'unknown')}`" v-if="r.stop_reason">{{ r.stop_reason }}</span>
        </div>
        <div class="ri-actions" v-if="r.actions && r.actions.length">
          <span class="ax" v-for="(a, i) in r.actions.slice(0, 6)" :key="i">{{ a }}</span>
        </div>
        <div class="ri-foot">
          <span>{{ vm.formatTime(r.started_at) }}</span>
          <span class="err" v-if="r.last_error" :title="r.last_error">⚠</span>
        </div>
      </button>
    </div>
  </section>
</template>

<style scoped>
.panel { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.panel-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.panel-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.count { font-size: 10px; color: #64748b; }
.tab-group { display: flex; gap: 4px; margin-left: auto; }
.tab { background: none; border: 1px solid #2d3149; color: #64748b; padding: 2px 10px; border-radius: 4px; font-size: 10px; cursor: pointer; transition: all .15s; }
.tab:hover { border-color: #475569; color: #cbd5e1; }
.tab.active { background: #7c3aed22; border-color: #7c3aed55; color: #a78bfa; }

.placeholder { font-size: 12px; color: #64748b; padding: 16px 0; text-align: center; }
.err-row { font-size: 12px; color: #fca5a5; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.retry { background: none; border: 1px solid #ef444444; color: #fca5a5; border-radius: 4px; padding: 2px 8px; font-size: 10px; cursor: pointer; }
.retry:hover { background: #ef444422; }

.run-items { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; max-height: 520px; padding-right: 2px; }
.run-item { text-align: left; background: #14161f; border: 1px solid #2d3149; border-radius: 8px; padding: 9px 11px; cursor: pointer; display: flex; flex-direction: column; gap: 5px; transition: all .15s; color: #cbd5e1; }
.run-item:hover { border-color: #475569; background: #1a1d27; }
.run-item.selected { border-color: #7c3aed77; background: #7c3aed18; box-shadow: 0 0 0 1px #7c3aed44 inset; }
.ri-top { display: flex; align-items: center; gap: 8px; }
.mode { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: .04em; }
.mode-reactive { background: #60a5fa22; color: #93c5fd; }
.mode-background { background: #a78bfa22; color: #c4b5fd; }
.mode-other { background: #64748b22; color: #94a3b8; }
.rid { font-size: 11px; color: #94a3b8; font-family: ui-monospace, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-mid { display: flex; flex-wrap: wrap; gap: 5px; }
.chip { font-size: 10px; padding: 1px 7px; border-radius: 3px; background: #2d3149; color: #cbd5e1; }
.chip.ghost { background: transparent; color: #64748b; border: 1px solid #2d3149; }
.chip.stop-ready { color: #86efac; }
.chip.stop-sleep, .chip.stop-timeout { color: #fde68a; }
.chip.stop-error, .chip.stop-fallback { color: #fca5a5; }
.ri-actions { display: flex; flex-wrap: wrap; gap: 4px; }
.ax { font-size: 9px; color: #a78bfa; background: #7c3aed1a; padding: 1px 5px; border-radius: 3px; }
.ri-foot { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: #64748b; }
.ri-foot .err { color: #fca5a5; }
</style>
