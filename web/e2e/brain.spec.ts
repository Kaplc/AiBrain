import { test, expect } from '@playwright/test'

/* Brain 观察台 E2E
 *
 * 覆盖 plan 测试验收：
 *   - /brain 页面加载、状态卡、run 列表、run 详情（有数据时）
 *   - 安全验收：页面加载 / 手动刷新 / 暂停刷新均不得请求 /brain/life/* 控制接口
 */
test.describe('Brain 观察台（只读）', () => {
  test('侧边栏可导航到 Brain 页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("大脑")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/brain/)
  })

  test('页面加载并展示状态面板与 run 列表', async ({ page }) => {
    const lifeCalls: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/brain/life/')) lifeCalls.push(`${req.method()} ${req.url()}`)
    })

    await page.goto('/brain', { waitUntil: 'networkidle' })
    await expect(page).toHaveURL(/\/brain/)
    await expect(page.locator('[data-testid="brain-page"]')).toBeVisible()
    await expect(page.locator('[data-testid="brain-status-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="brain-run-list"]')).toBeVisible()
    await expect(page.locator('[data-testid="brain-pending-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="brain-gate-panel"]')).toBeVisible()

    // 安全验收：页面加载不得调用任何 /brain/life/*（start/stop/tick）控制接口
    expect(lifeCalls).toEqual([])
  })

  test('加载时发起只读 state 与 runs/recent 请求', async ({ page }) => {
    const seen: string[] = []
    page.on('request', (req) => {
      const u = req.url()
      if (u.includes('/brain/state')) seen.push('state')
      if (u.includes('/brain/runs/recent')) seen.push('recent')
    })

    await page.goto('/brain', { waitUntil: 'networkidle' })
    expect(seen).toContain('state')
    expect(seen).toContain('recent')
  })

  test('手动刷新只发起只读 GET，不触发 life 控制接口', async ({ page }) => {
    await page.goto('/brain', { waitUntil: 'networkidle' })

    const lifeCalls: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/brain/life/')) lifeCalls.push(`${req.method()} ${req.url()}`)
    })

    await page.locator('[data-testid="brain-refresh-btn"]').click()
    await page.waitForTimeout(1500)

    expect(lifeCalls).toEqual([])
  })

  test('点击 run 可加载详情（无 run 记录时跳过）', async ({ page }) => {
    await page.goto('/brain', { waitUntil: 'networkidle' })
    await page.waitForTimeout(400)

    const firstRun = page.locator('[data-testid="brain-run-item"]').first()
    const count = await firstRun.count()
    // 系统空闲、无 run 记录：环境前置条件不满足，跳过而非失败
    test.skip(count === 0, '暂无 run 记录，跳过详情加载断言')

    await firstRun.click()
    await expect(page.locator('[data-testid="brain-run-detail"]')).toBeVisible()
  })

  test('暂停自动刷新后停止轮询 state', async ({ page }) => {
    await page.goto('/brain', { waitUntil: 'networkidle' })
    // 切换为暂停（按钮文案变为「自动刷新已暂停」）
    await page.locator('[data-testid="brain-autorefresh-toggle"]').click()
    await expect(page.locator('[data-testid="brain-autorefresh-toggle"]')).toContainText('已暂停')

    let polled = false
    page.on('request', (req) => {
      if (req.url().includes('/brain/state')) polled = true
    })
    // 刷新间隔 4000ms，等 5500ms 确认不再轮询
    await page.waitForTimeout(5500)
    expect(polled).toBe(false)
  })
})
