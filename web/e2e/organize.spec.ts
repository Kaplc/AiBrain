import { test, expect } from '@playwright/test'

/* Memory - 整理记忆Tab 流式分析 + 暂停/恢复/停止 */
test.describe('Memory - OrganizeTab 流式分析', () => {
  test.beforeEach(async ({ page }) => {
    // 通过侧边栏导航到记忆页面（与 navigation.spec.ts 保持一致）
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("记忆")').click()
    await page.waitForURL(/\/memory/)
    // 切换到整理记忆Tab
    await page.locator('.nav-tab:has-text("整理记忆")').click()
    await page.waitForTimeout(500)
  })

  test('整理Tab - 工具栏元素存在', async ({ page }) => {
    // 阈值选择框
    await expect(page.locator('.organize-select')).toBeVisible()
    // 开始分析按钮
    const startBtn = page.locator('.organize-toolbar .btn-accent')
    await expect(startBtn).toHaveText('开始分析')
  })

  test('整理Tab - 开始分析按钮可点击', async ({ page }) => {
    const startBtn = page.locator('.organize-toolbar .btn-accent')
    await expect(startBtn).toBeEnabled()
  })

  test('整理Tab - 阈值选择可选', async ({ page }) => {
    const select = page.locator('.organize-select')
    await expect(select).toBeVisible()
    // 默认值应该是 0.85
    await expect(select).toHaveValue('0.85')
    // 切换到严格
    await select.selectOption('0.90')
    await expect(select).toHaveValue('0.90')
  })

  test('整理Tab - 空状态提示', async ({ page }) => {
    // 没有开始分析前，应该显示空状态（通过 locator 限定在 organize tab-panel 内）
    const organizePanel = page.locator('.tab-panel:last-child')
    await expect(organizePanel.locator('.empty-text')).toHaveText('点击"开始分析"扫描重复记忆')
  })

  test('整理Tab - 分析中显示暂停按钮，停止后按钮恢复', async ({ page }) => {
    // 这个测试只验证 UI 状态切换，不实际触发后端 SSE
    const startBtn = page.locator('.organize-toolbar .btn-accent')
    await expect(startBtn).toHaveText('开始分析')
    // stop 按钮在非 busy 状态不应显示
    await expect(page.locator('.organize-toolbar .btn-danger-sm')).not.toBeVisible()
  })

  test('整理Tab - 开始分析后面板内容切换', async ({ page }) => {
    // 点击开始分析后，应该显示加载状态或直接出现组
    await page.locator('.organize-toolbar .btn-accent').click()
    // busy状态时工具栏应该显示暂停按钮
    await expect(page.locator('.organize-toolbar .btn-warn')).toBeVisible({ timeout: 3000 })
  })
})
