/* BrainView 类型定义
 *
 * 对应后端 main_brain 契约（contracts.py / pending_expression.py / brain_routes.py）。
 * 字段尽量对齐实际响应，缺失字段一律可选，渲染时做兜底，避免后端结构微调导致白屏。
 */

// ── LifeState（contracts.default_life_state + state adapter 合并字段）──────
export interface BrainMood {
  valence?: number
  arousal?: number
  label?: string
}

export interface PendingExpression {
  id?: string
  type?: string
  source_node_id?: string
  expression_score?: number
  source?: string
  created_at?: string
  expressed?: boolean
  note?: string
}

export interface LifeState {
  life_loop_status?: string
  current_activity?: string
  current_focus?: string
  focus_since?: string
  last_activity_at?: string
  last_user_contact_at?: string
  idle_seconds?: number
  autonomy_level?: string
  energy?: number
  mood?: BrainMood
  working_set?: any[]
  open_loops?: any[]
  goals?: any[]
  recent_thoughts?: any[]
  pending_expressions?: PendingExpression[]
  relationship_context?: any
  self_narrative_summary?: string
  last_proactive_contact_at?: string
  next_wake_hint?: any
  last_error?: string
}

// ── 配置（brain_routes /brain/state.config）──────────────────────────────
export interface BrainConfig {
  brain_session_enabled?: boolean
  life_loop_enabled?: boolean
  proactive_contact_enabled?: boolean
  autonomy_level?: string
}

// ── /brain/state 响应 ─────────────────────────────────────────────────────
export interface BrainStateResponse {
  life_state: LifeState
  scheduler_running: boolean
  config: BrainConfig
  last_reactive_run_id?: string
  last_background_run_id?: string
  log_path?: string
  error?: string
}

// ── run 摘要（BrainRun.to_summary，/brain/runs/recent）─────────────────────
export type RunMode = 'reactive' | 'background'

export interface BrainRunSummary {
  run_id: string
  mode?: RunMode | string
  trigger?: any
  started_at?: string
  finished_at?: string
  cycle_count?: number
  selected_activity?: string
  actions?: string[]
  stop_reason?: string
  last_error?: string
  // 可选补充字段（部分响应会带）
  thought_summary?: string
  error_count?: number
}

// ── 单轮 cycle（BrainCycle.to_dict，/brain/runs/<id>.cycles[]）──────────────
export interface BrainCycle {
  cycle_index: number
  thought_summary?: string
  focus?: string
  action?: string
  action_args?: any
  result_summary?: string
  reply_ready?: boolean
  notify_candidate?: any
  confidence?: number
  latency_ms?: number
  error?: string
}

// ── run 详情（BrainRun.to_full，/brain/runs/<id>）──────────────────────────
export interface BrainRunDetail {
  run_id: string
  mode?: RunMode | string
  trigger?: any
  started_at?: string
  finished_at?: string
  selected_activity?: string
  cycles?: BrainCycle[]
  memory_context_count?: number
  tool_results?: any[]
  state_deltas?: any[]
  pending_created?: any[]
  final_strategy?: any
  learning_hints?: string[]
  stop_reason?: string
  error?: string
}

export type ModeFilter = 'all' | RunMode
