<script setup lang="ts">
/* run 详情 + cycle 时间线。数据来自 /brain/runs/<id>（vm.selectedRun，按需加载）。
 * 长 action_args / tool_results / final_strategy 默认折叠（FR-014）。纯只读。 */
import { ref } from 'vue'
import { brainViewModel as vm } from '../BrainViewModel'
import type { BrainCycle } from '../types'

// 每个 cycle 的 action_args 折叠状态（按 cycle_index 记录）
const expandedArgs = ref<Record<number, boolean>>({})
const showMeta = ref(false)

function toggleArgs(idx: number) { expandedArgs.value[idx] = !expandedArgs.value[idx] }
function argsText(c: BrainCycle): string {
  const a = c.action_args
  if (a == null) return ''
  try { return typeof a === 'string' ? a : JSON.stringify(a, null, 2) } catch { return String(a) }
}
function cycleIdx(c: BrainCycle): number {
  return c.cycle ?? c.cycle_index
}
function cycleThought(c: BrainCycle): string {
  return c.thought || c.thought_summary || ''
}
function isConsciousness(c: BrainCycle): boolean {
  return c.cycle !== undefined || ['think','speak','rest','create_activity','set_activity','use_tool'].includes(c.action || '')
}
function actionCls(action?: string): string {
  if (!action) return ''
  if (action === 'final_reply' || action === 'create_pending' || action === 'speak') return 'ax-send'
  if (['recall_memory','use_tool','memory_search','web_search','read_file','grep_search','store_memory','list_files'].includes(action)) return 'ax-active'
  if (['think','rest','wait'].includes(action)) return 'ax-idle'
  if (['create_activity','set_activity'].includes(action)) return 'ax-create'
  if (action === 'abort' || action === 'error') return 'ax-err'
  return ''
}
</script>

<template>
  <section class="panel run-detail" data-testid="brain-run-detail">
    <div class="panel-head">
      <span class="panel-title">循环详情</span>
      <span class="sub" v-if="vm.selectedRun.value">{{ vm.selectedRun.value.mode || '--' }} · {{ vm.selectedRun.value.cycles?.length || 0 }} cycles</span>
      <button v-if="vm.selectedRunId.value" class="mini-refresh" @click="vm.loadDetail(vm.selectedRunId.value)"
        :disabled="vm.loadingDetail.value" title="刷新该 run 详情" data-testid="brain-detail-refresh">↻</button>
    </div>

    <div v-if="vm.loadingDetail.value && !vm.selectedRun.value" class="placeholder">加载详情中…</div>
    <div v-else-if="vm.errorDetail.value" class="err-row" data-testid="brain-detail-error">
      详情读取失败：{{ vm.errorDetail.value }}
    </div>
    <div v-else-if="!vm.selectedRun.value" class="placeholder">点击左侧某条循环查看逐轮动作链</div>

    <template v-else>
      <!-- run 头部 -->
      <div class="run-head">
        <div class="rh-id" :title="vm.selectedRun.value.run_id">{{ vm.selectedRun.value.run_id }}</div>
        <div class="rh-meta">
          <span class="chip" v-if="vm.selectedRun.value.selected_activity">{{ vm.selectedRun.value.selected_activity }}</span>
          <span class="chip" :class="`stop-${(vm.selectedRun.value.stop_reason || 'unknown')}`" v-if="vm.selectedRun.value.stop_reason">
            停止：{{ vm.selectedRun.value.stop_reason }}
          </span>
        </div>
        <div class="rh-time">
          <span>开始 {{ vm.formatTime(vm.selectedRun.value.started_at) }}</span>
          <span>结束 {{ vm.formatTime(vm.selectedRun.value.finished_at) }}</span>
        </div>
      </div>

      <!-- cycle 时间线 -->
      <div class="timeline" v-if="vm.selectedRun.value.cycles?.length" data-testid="brain-cycle-timeline">
        <div v-for="c in vm.selectedRun.value.cycles" :key="cycleIdx(c)" class="cycle" data-testid="brain-cycle-item">
          <div class="cy-dot" :class="actionCls(c.action)"></div>
          <div class="cy-body">
            <div class="cy-top">
              <span class="cy-idx">#{{ cycleIdx(c) }}</span>
              <span class="cy-action" :class="actionCls(c.action)" v-if="c.action">{{ c.action }}</span>
              <!-- 旧 reactive 字段 -->
              <span class="cy-conf" v-if="typeof c.confidence === 'number'">置信 {{ vm.formatScore(c.confidence) }}</span>
              <span class="cy-lat" v-if="typeof c.latency_ms === 'number' && c.latency_ms > 0">{{ Math.round(c.latency_ms) }}ms</span>
              <span class="cy-flag" v-if="c.reply_ready">待回复</span>
            </div>
            <!-- 新 consciousness 字段 -->
            <div class="cy-tool" v-if="isConsciousness(c) && c.tool_name">
              <span class="k">tool</span>{{ c.tool_name }}<span v-if="c.tool_args">({{ c.tool_args }})</span>
            </div>
            <div class="cy-activity" v-if="isConsciousness(c) && c.activity">
              <span class="k">activity</span>{{ c.activity }}<span v-if="c.activity_context">: {{ c.activity_context }}</span>
            </div>
            <div class="cy-content" v-if="isConsciousness(c) && c.content">
              <span class="k">speak</span>{{ c.content }}
            </div>
            <!-- 思考内容（兼容新旧字段名） -->
            <div class="cy-thought" v-if="cycleThought(c)">{{ cycleThought(c) }}</div>
            <!-- 旧 reactive 字段 -->
            <div class="cy-focus" v-if="c.focus"><span class="k">focus</span>{{ c.focus }}</div>
            <div class="cy-result" v-if="c.result_summary"><span class="k">result</span>{{ c.result_summary }}</div>
            <div class="cy-err" v-if="c.error">⚠ {{ c.error }}</div>

            <button v-if="c.action_args && Object.keys(c.action_args).length" class="toggle" @click="toggleArgs(cycleIdx(c))">
              {{ expandedArgs[cycleIdx(c)] ? '▾ 收起参数' : '▸ 展开参数' }}
            </button>
            <pre v-if="c.action_args && Object.keys(c.action_args).length && expandedArgs[cycleIdx(c)]" class="cy-args">{{ argsText(c) }}</pre>
          </div>
        </div>
      </div>
      <div v-else class="placeholder small">该循环没有 cycle 记录</div>

      <!-- 可折叠的运行级元信息 -->
      <button class="toggle meta-toggle" @click="showMeta = !showMeta">
        {{ showMeta ? '▾ 收起运行元信息' : '▸ 展开运行元信息（记忆/工具/状态变更）' }}
      </button>
      <div v-if="showMeta" class="meta-block">
        <div class="meta-line"><span class="k">召回记忆</span>{{ vm.selectedRun.value.memory_context_count ?? 0 }} 条</div>
        <div class="meta-line"><span class="k">工具结果</span>{{ vm.selectedRun.value.tool_results?.length || 0 }} 条</div>
        <div class="meta-line"><span class="k">状态变更</span>{{ vm.selectedRun.value.state_deltas?.length || 0 }} 项</div>
        <div class="meta-line"><span class="k">新建 pending</span>{{ vm.selectedRun.value.pending_created?.length || 0 }} 条</div>
        <pre v-if="vm.selectedRun.value.final_strategy && Object.keys(vm.selectedRun.value.final_strategy).length" class="cy-args">{{ JSON.stringify(vm.selectedRun.value.final_strategy, null, 2) }}</pre>
      </div>
    </template>
  </section>
</template>

<style scoped>
.panel { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.panel-head { display: flex; align-items: center; gap: 8px; }
.panel-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.sub { font-size: 10px; color: #64748b; }
.mini-refresh { margin-left: auto; background: none; border: 1px solid #2d3149; color: #64748b; cursor: pointer; font-size: 12px; width: 24px; height: 24px; border-radius: 5px; }
.mini-refresh:hover:not(:disabled) { color: #cbd5e1; border-color: #475569; background: #1e293b; }
.mini-refresh:disabled { opacity: .5; cursor: default; }

.placeholder { font-size: 12px; color: #64748b; padding: 24px 0; text-align: center; }
.placeholder.small { padding: 10px 0; }
.err-row { font-size: 12px; color: #fca5a5; }

.run-head { display: flex; flex-direction: column; gap: 6px; padding-bottom: 8px; border-bottom: 1px solid #2d3149; }
.rh-id { font-size: 12px; color: #cbd5e1; font-family: ui-monospace, monospace; word-break: break-all; }
.rh-meta { display: flex; flex-wrap: wrap; gap: 5px; }
.rh-time { display: flex; gap: 16px; font-size: 10px; color: #64748b; }
.chip { font-size: 10px; padding: 1px 7px; border-radius: 3px; background: #2d3149; color: #cbd5e1; }
.chip.stop-ready { color: #86efac; }
.chip.stop-sleep, .chip.stop-timeout { color: #fde68a; }
.chip.stop-error, .chip.stop-fallback { color: #fca5a5; }

.timeline { display: flex; flex-direction: column; gap: 0; overflow-y: auto; max-height: 560px; padding-right: 2px; }
.cycle { display: flex; gap: 10px; padding: 8px 0; position: relative; }
.cycle::before { content: ''; position: absolute; left: 4px; top: 18px; bottom: -8px; width: 1px; background: #2d3149; }
.cycle:last-child::before { display: none; }
.cy-dot { width: 9px; height: 9px; border-radius: 50%; background: #7c3aed; margin-top: 4px; flex-shrink: 0; z-index: 1; box-shadow: 0 0 0 2px #1a1d27; }
.cy-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.cy-top { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.cy-idx { font-size: 11px; font-weight: 700; color: #94a3b8; }
.cy-action { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px; background: #2d3149; color: #cbd5e1; }
.cy-action.ax-send { color: #86efac; background: #22c55e22; }
.cy-action.ax-active { color: #93c5fd; background: #60a5fa22; }
.cy-action.ax-idle { color: #fde68a; background: #eab30822; }
.cy-action.ax-create { color: #c4b5fd; background: #7c3aed22; }
.cy-action.ax-err { color: #fca5a5; background: #ef444422; }
.cy-dot.ax-active { background: #60a5fa; }
.cy-dot.ax-send { background: #22c55e; }
.cy-dot.ax-create { background: #7c3aed; }
.cy-dot.ax-idle { background: #eab308; }
.cy-conf, .cy-lat { font-size: 9px; color: #64748b; }
.cy-flag { font-size: 9px; color: #a78bfa; border: 1px solid #7c3aed55; border-radius: 3px; padding: 0 5px; }
.cy-thought { font-size: 12px; color: #e2e8f0; }
.cy-focus, .cy-result, .cy-tool, .cy-activity, .cy-content { font-size: 11px; color: #94a3b8; word-break: break-word; }
.cy-tool .k, .cy-activity .k, .cy-content .k, .cy-focus .k, .meta-line .k { color: #64748b; margin-right: 5px; font-size: 10px; }
.cy-err { font-size: 11px; color: #fca5a5; }

.toggle { align-self: flex-start; background: none; border: none; color: #7c3aed; font-size: 10px; cursor: pointer; padding: 2px 0; }
.toggle:hover { color: #a78bfa; }
.cy-args { font-size: 10px; color: #94a3b8; background: #14161f; border: 1px solid #2d3149; border-radius: 6px; padding: 8px 10px; margin: 4px 0 0; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, monospace; }
.meta-toggle { margin-top: 4px; }
.meta-block { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: #94a3b8; padding: 8px 10px; background: #14161f; border: 1px solid #2d3149; border-radius: 6px; }
</style>
