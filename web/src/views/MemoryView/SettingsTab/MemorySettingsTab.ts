/* 记忆设置 Tab
 *
 * infer 开关已移除 — LLM 编码固定开启（自动提取情景节点 + 图增强搜索）
 */

import { ref } from 'vue'

export class MemorySettingsTab {
  /** 是否正在加载 */
  readonly loading = ref(false)
  /** 是否正在保存 */
  readonly saving = ref(false)

  async load(): Promise<void> {
    this.loading.value = true
    // 无需加载设置，所有功能固定启用
    this.loading.value = false
  }

  async save(): Promise<void> {
    // 无设置项可保存
  }
}
