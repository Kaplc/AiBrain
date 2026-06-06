/* 设置视图模型 - 动态 Tab 注册（集中入口）
 *
 * 作用：作为 SettingsView 的顶层 ViewModel，通过 TabRegistry 动态发现和组合各 Tab
 * 实现：从 window 注册表获取所有 Tab，提供统一的配置加载和 Tab 切换接口
 *
 * 新增 Tab 步骤：
 * 1. 在 SettingsView/ 下创建新文件夹，如 MyTab/
 * 2. 放入 MyTab.vue（模板）和 MyTab.ts（逻辑类）
 * 3. 在 TabRegistry.ts 中添加一行 import 即可自动注册
 */

import { ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { getAllTabs, TabDef } from './TabRegistry'

export class SettingsViewModel {
  readonly activeTab = ref<string>('model')

  /* tabList：获取所有已注册的 Tab（从 window 注册表） */
  get tabList(): TabDef[] { return getAllTabs() }

  // 直接引用各 Tab 实例（从 tabList 中解析，保持与旧代码兼容）
  get modelTab() { return this.tabList.find(t => t.name === 'model')?.tabClass }
  get mem0Tab() { return this.tabList.find(t => t.name === 'mem0')?.tabClass }
  get wikiTab() { return this.tabList.find(t => t.name === 'wiki')?.tabClass }
  get llmTab() { return this.tabList.find(t => t.name === 'llm')?.tabClass }
  get chatTab() { return this.tabList.find(t => t.name === 'chat')?.tabClass }

  private _configStore = useConfigStore()

  /* switchTab：切换激活的 Tab */
  switchTab(tab: string): void {
    this.activeTab.value = tab
  }

  /* getTab：根据名称获取 Tab 定义 */
  getTab(name: string): TabDef | undefined {
    return this.tabList.find(t => t.name === name)
  }

  /* inputType：根据字段类型返回 HTML input type
   * 流程：password → password，number → number，其他 → text
   */
  inputType(type: string): string {
    if (type === 'password') return 'password'
    if (type === 'number') return 'number'
    return 'text'
  }

  /* onMounted：组件挂载时的初始化
   * 流程：加载全部配置 → 遍历所有 Tab 调用 loadFromConfig
   */
  async onMounted(): Promise<void> {
    console.log('[SettingsView] mounted')
    await this.loadAll()
  }

  /* loadAll：加载所有 Tab 的配置
   * 流程：configStore.loadConfig() → 解析 cfg/st/aibrain → 遍历 tabList 调用各 Tab 的 loadFromConfig
   */
  async loadAll(): Promise<void> {
    try {
      const result = await this._configStore.loadConfig()
      if (!result) return
      const { cfg, st, aibrain } = result

      for (const tabDef of this.tabList) {
        tabDef.tabClass.loadFromConfig?.(cfg, st, aibrain)
      }
    } catch (e) {
      console.error('[SettingsView] loadAll error:', e)
    }
  }

  /* initDirChecks：初始化所有 Tab 的目录校验状态 */
  initDirChecks(): void {
    for (const tabDef of this.tabList) {
      tabDef.tabClass.initDirChecks?.()
    }
  }
}

export const settingsViewModel = new SettingsViewModel()

// 预先触发各 Tab 的注册（通过 TabRegistry）
import TabRegistry from './TabRegistry'
