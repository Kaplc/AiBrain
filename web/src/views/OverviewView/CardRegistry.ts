/* 卡片注册中心
 *
 * 作用：集中管理 OverviewView 中的所有卡片，支持动态注册和发现
 * 实现：利用 window 全局对象存储卡片定义，避免 ES module 加载顺序问题
 *
 * 新增卡片步骤：
 * 1. 在 OverviewView/ 下创建新文件夹，如 MyCard/
 * 2. 放入 MyCard.vue（模板）和 MyCard.ts（逻辑类，调用 registerCard 注册）
 * 3. 在 CardRegistry.ts 中添加一行 import 即可自动注册
 */
import type { Component } from 'vue'

export interface CardDef {
  name: string
  component: Component
  cardClass: any
}

/* registerCard：注册卡片到全局注册表
 * 流程：在 window 上创建/获取 __overviewCardRegistry__ 数组 → 推入卡片定义
 * 作用：替代 import 顺序依赖，确保各卡片模块可独立注册
 */
export function registerCard(def: CardDef): void {
  const key = '__overviewCardRegistry__'
  if (!(key in window)) (window as any)[key] = []
  ;(window as any)[key].push(def)
}

/* getAllCards：获取所有已注册的卡片列表
 * 返回：CardDef[] 数组的拷贝
 */
export function getAllCards(): CardDef[] {
  const key = '__overviewCardRegistry__'
  return (window as any)[key] ? [...(window as any)[key]] : []
}

// ===== 导入即注册 =====
import './ModelCard/ModelCard'
import './QdrantCard/QdrantCard'
import './FlaskCard/FlaskCard'
import './DeviceCard/DeviceCard'
// import './BalanceCard/BalanceCard'
// import './TokenCard/TokenCard'