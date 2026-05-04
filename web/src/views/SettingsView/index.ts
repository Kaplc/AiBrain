/* 设置视图模型 - 动态 Tab 注册（集中入口）
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

  get tabList(): TabDef[] { return getAllTabs() }

  // 直接引用各 Tab 实例（从 tabList 中解析，保持与旧代码兼容）
  get modelTab() { return this.tabList.find(t => t.name === 'model')?.tabClass }
  get mem0Tab() { return this.tabList.find(t => t.name === 'mem0')?.tabClass }
  get wikiTab() { return this.tabList.find(t => t.name === 'wiki')?.tabClass }

  private _configStore = useConfigStore()

  switchTab(tab: string): void {
    this.activeTab.value = tab
  }

  getTab(name: string): TabDef | undefined {
    return this.tabList.find(t => t.name === name)
  }

  inputType(type: string): string {
    if (type === 'password') return 'password'
    if (type === 'number') return 'number'
    return 'text'
  }

  async onMounted(): Promise<void> {
    console.log('[SettingsView] mounted')
    await this.loadAll()
  }

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

  initDirChecks(): void {
    for (const tabDef of this.tabList) {
      tabDef.tabClass.initDirChecks?.()
    }
  }
}

export const settingsViewModel = new SettingsViewModel()

// 预先触发各 Tab 的注册（通过 TabRegistry）
import TabRegistry from './TabRegistry'
