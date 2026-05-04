/* 卡片注册中心
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

// 使用 window 全局对象存储卡片，完全避免 ES module 加载顺序问题
export function registerCard(def: CardDef): void {
  const key = '__overviewCardRegistry__'
  if (!(key in window)) (window as any)[key] = []
  ;(window as any)[key].push(def)
}

export function getAllCards(): CardDef[] {
  const key = '__overviewCardRegistry__'
  return (window as any)[key] ? [...(window as any)[key]] : []
}

// ===== 导入即注册 =====
import './ModelCard/ModelCard'
import './QdrantCard/QdrantCard'
import './FlaskCard/FlaskCard'
import './DeviceCard/DeviceCard'