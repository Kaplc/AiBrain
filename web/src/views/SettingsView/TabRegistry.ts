/* Tab 注册表 - 集中管理
 *
 * 新增 Tab 步骤：
 * 1. 在 SettingsView/ 下创建新文件夹，如 MyTab/
 * 2. 放入 MyTab.vue（模板）和 MyTab.ts（逻辑类）
 * 3. 在 TabRegistry.ts 中添加一行 import 即可自动注册
 */
import type { Component } from 'vue'

export interface TabDef {
  name: string
  title: string
  component: Component
  tabClass: any
  onMounted?: () => void
  onDirChecksInit?: () => void
}

// 使用 window 全局对象存储，完全避免 ES module 加载顺序问题
export function registerTab(def: TabDef): void {
  const key = '__settingsTabRegistry__'
  if (!(key in window)) (window as any)[key] = []
  ;(window as any)[key].push(def)
}

export function getAllTabs(): TabDef[] {
  const key = '__settingsTabRegistry__'
  return (window as any)[key] ? [...(window as any)[key]] : []
}

// ===== 导入即注册 =====
import './ModelTab/ModelTab'
import './Mem0Tab/Mem0Tab'
import './WikiTab/WikiTab'