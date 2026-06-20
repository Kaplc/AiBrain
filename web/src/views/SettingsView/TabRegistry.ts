/* Tab 注册表 - 集中管理
 *
 * 作用：集中管理 SettingsView 中的所有 Tab，支持动态注册和发现
 * 实现：利用 window 全局对象存储 Tab 定义，避免 ES module 加载顺序问题
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

/* registerTab：注册 Tab 到全局注册表
 * 流程：在 window 上创建/获取 __settingsTabRegistry__ 数组 → 推入 Tab 定义
 */
export function registerTab(def: TabDef): void {
  const key = '__settingsTabRegistry__'
  if (!(key in window)) (window as any)[key] = []
  ;(window as any)[key].push(def)
}

/* getAllTabs：获取所有已注册的 Tab 列表
 * 返回：TabDef[] 数组的拷贝
 */
export function getAllTabs(): TabDef[] {
  const key = '__settingsTabRegistry__'
  return (window as any)[key] ? [...(window as any)[key]] : []
}

// ===== 导入即注册 =====
import './ModelTab/ModelTab'
// import './Mem0Tab/Mem0Tab'
// import './WikiTab/WikiTab'
import './LLMTab/LLMTab'
// import './ChatTab/ChatTab'
// import './StatsTab/StatsTab'