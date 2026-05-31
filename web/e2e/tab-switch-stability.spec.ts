import { test, expect } from '@playwright/test'

/* 记忆图谱 Tab 切换稳定性 E2E 测试
 *
 * 测试目标：验证 /memory 页面六个 Tab（搜索记忆、保存记忆、合并记忆、设置、实体、图谱）
 * 之间的切换稳定性——快速来回切换不崩溃、面板正确显示/隐藏、active 状态正确。
 *
 * Tab 面板映射：
 *   搜索记忆 → .tab-panel:has(.search-bar)
 *   保存记忆 → .tab-panel:has(.store-area)
 *   合并记忆 → .tab-panel:has(.organize-toolbar)
 *   设置     → .settings-panel
 *   实体     → .entity-panel
 *   图谱     → .graph-panel
 */

// ── helpers ──

/** 所有 Tab 定义：按钮文本 + 面板选择器 */
const TABS = [
  { name: '搜索记忆', panel: '.tab-panel:has(.search-bar)' },
  { name: '保存记忆', panel: '.tab-panel:has(.store-area)' },
  { name: '合并记忆', panel: '.tab-panel:has(.organize-toolbar)' },
  { name: '设置', panel: '.settings-panel' },
  { name: '实体', panel: '.entity-panel' },
  { name: '图谱', panel: '.graph-panel' },
] as const

/** 点击指定 Tab 并等待对应面板可见 */
async function switchToTab(page: import('@playwright/test').Page, name: string, panelSelector: string) {
  const tab = page.locator(`.nav-tab:has-text("${name}")`)
  await tab.click()
  await expect(page.locator(panelSelector)).toBeVisible({ timeout: 5000 })
}

// ============================================================================
// 1. 每个 Tab 可点击且面板可见
// ============================================================================

test.describe('Tab 基本渲染', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
  })

  test('导航栏包含全部六个 Tab 按钮', async ({ page }) => {
    const tabs = page.locator('.nav-tab')
    await expect(tabs).toHaveCount(6)
  })

  for (const tab of TABS) {
    test(`点击「${tab.name}」Tab 后面板可见`, async ({ page }) => {
      await switchToTab(page, tab.name, tab.panel)
    })
  }

  test('默认激活 Tab 为「搜索记忆」', async ({ page }) => {
    const activeTab = page.locator('.nav-tab.active')
    await expect(activeTab).toHaveText('搜索记忆')
  })
})

// ============================================================================
// 2. Active 状态正确切换
// ============================================================================

test.describe('Active 状态验证', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
  })

  for (const tab of TABS) {
    test(`点击「${tab.name}」后 active 类正确`, async ({ page }) => {
      await page.locator(`.nav-tab:has-text("${tab.name}")`).click()
      const activeTab = page.locator('.nav-tab.active')
      await expect(activeTab).toHaveText(tab.name)
    })
  }

  test('切换 Tab 后前一个 Tab 的 active 消失', async ({ page }) => {
    // 先切到图谱
    await page.locator('.nav-tab:has-text("图谱")').click()
    await expect(page.locator('.nav-tab.active')).toHaveText('图谱')

    // 再切到实体
    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.nav-tab.active')).toHaveText('实体')

    // 图谱 Tab 不再有 active
    await expect(page.locator('.nav-tab:has-text("图谱")')).not.toHaveClass(/active/)
  })
})

// ============================================================================
// 3. 两两切换稳定性
// ============================================================================

test.describe('两两 Tab 切换', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
  })

  test('搜索记忆 ↔ 图谱 来回切换', async ({ page }) => {
    const searchPanel = page.locator('.tab-panel:has(.search-bar)')
    const graphPanel = page.locator('.graph-panel')

    // 初始状态：搜索可见
    await expect(searchPanel).toBeVisible()

    // 切到图谱
    await switchToTab(page, '图谱', '.graph-panel')
    await expect(searchPanel).not.toBeVisible()

    // 切回搜索
    await switchToTab(page, '搜索记忆', '.tab-panel:has(.search-bar)')
    await expect(graphPanel).not.toBeVisible()
  })

  test('保存记忆 ↔ 实体 来回切换', async ({ page }) => {
    const storePanel = page.locator('.tab-panel:has(.store-area)')
    const entityPanel = page.locator('.entity-panel')

    await switchToTab(page, '保存记忆', '.tab-panel:has(.store-area)')
    await expect(storePanel).toBeVisible()

    await switchToTab(page, '实体', '.entity-panel')
    await expect(storePanel).not.toBeVisible()
    await expect(entityPanel).toBeVisible()

    await switchToTab(page, '保存记忆', '.tab-panel:has(.store-area)')
    await expect(entityPanel).not.toBeVisible()
  })

  test('合并记忆 ↔ 设置 来回切换', async ({ page }) => {
    const organizePanel = page.locator('.tab-panel:has(.organize-toolbar)')
    const settingsPanel = page.locator('.settings-panel')

    await switchToTab(page, '合并记忆', '.tab-panel:has(.organize-toolbar)')
    await expect(organizePanel).toBeVisible()

    await switchToTab(page, '设置', '.settings-panel')
    await expect(organizePanel).not.toBeVisible()
    await expect(settingsPanel).toBeVisible()

    await switchToTab(page, '合并记忆', '.tab-panel:has(.organize-toolbar)')
    await expect(settingsPanel).not.toBeVisible()
  })

  test('图谱 ↔ 实体 来回切换', async ({ page }) => {
    const graphPanel = page.locator('.graph-panel')
    const entityPanel = page.locator('.entity-panel')

    await switchToTab(page, '图谱', '.graph-panel')
    await expect(graphPanel).toBeVisible()

    await switchToTab(page, '实体', '.entity-panel')
    await expect(graphPanel).not.toBeVisible()
    await expect(entityPanel).toBeVisible()

    await switchToTab(page, '图谱', '.graph-panel')
    await expect(entityPanel).not.toBeVisible()
    await expect(graphPanel).toBeVisible()
  })
})

// ============================================================================
// 4. 快速连续切换不崩溃
// ============================================================================

test.describe('快速连续切换', () => {
  test('快速遍历全部 Tab 不崩溃', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    // 快速按顺序点击每个 Tab
    for (const tab of TABS) {
      await page.locator(`.nav-tab:has-text("${tab.name}")`).click()
    }

    // 停在最后一个 Tab（图谱），验证面板可见
    await expect(page.locator('.graph-panel')).toBeVisible({ timeout: 5000 })
  })

  test('快速来回切换图谱和实体 5 次不崩溃', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    for (let i = 0; i < 5; i++) {
      await page.locator('.nav-tab:has-text("图谱")').click()
      await page.locator('.nav-tab:has-text("实体")').click()
    }

    // 最终停在实体，验证状态正确
    await expect(page.locator('.entity-panel')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.nav-tab.active')).toHaveText('实体')
  })

  test('随机顺序切换后回到搜索记忆', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    // 切换到多个不同的 Tab
    await page.locator('.nav-tab:has-text("图谱")').click()
    await page.locator('.nav-tab:has-text("保存记忆")').click()
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.nav-tab:has-text("设置")').click()

    // 切回搜索记忆
    await switchToTab(page, '搜索记忆', '.tab-panel:has(.search-bar)')
    await expect(page.locator('.nav-tab.active')).toHaveText('搜索记忆')
    await expect(page.locator('.tab-panel:has(.search-bar)')).toBeVisible()
  })
})

// ============================================================================
// 5. 面板内容完整性——切换后关键元素存在
// ============================================================================

test.describe('切换后面板内容完整', () => {
  test('切到搜索记忆后搜索栏可用', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    // 先离开再回来
    await page.locator('.nav-tab:has-text("图谱")').click()
    await switchToTab(page, '搜索记忆', '.tab-panel:has(.search-bar)')

    const input = page.locator('input[placeholder="搜索相关记忆..."]')
    await expect(input).toBeVisible()
    await expect(input).toBeEnabled()
  })

  test('切到保存记忆后文本域可用', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    await switchToTab(page, '保存记忆', '.tab-panel:has(.store-area)')

    const textarea = page.locator('.store-area textarea')
    await expect(textarea).toBeVisible()
    await expect(textarea).toBeEnabled()
  })

  test('切到实体后统计卡片渲染', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    await switchToTab(page, '实体', '.entity-panel')
    await expect(page.locator('.entity-panel .stat-card').first()).toBeVisible({ timeout: 5000 })
  })

  test('切到图谱后 graph-container 渲染', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    await switchToTab(page, '图谱', '.graph-panel')
    await page.waitForTimeout(2000)
    await expect(page.locator('.graph-container')).toBeVisible({ timeout: 5000 })
  })
})

// ============================================================================
// 6. 刷新按钮后 Tab 状态保持
// ============================================================================

test.describe('刷新后状态保持', () => {
  test('刷新按钮点击后不切换 Tab', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    // 切到图谱
    await switchToTab(page, '图谱', '.graph-panel')

    // 点击顶部刷新按钮
    const refreshBtn = page.locator('.nav-stat .btn-icon')
    await refreshBtn.click()

    // 仍在图谱 Tab
    await expect(page.locator('.nav-tab.active')).toHaveText('图谱')
    await expect(page.locator('.graph-panel')).toBeVisible()
  })
})
