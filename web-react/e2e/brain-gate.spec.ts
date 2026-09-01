/* 大脑页（TC-BRAIN）+ Gate 页（TC-GATE）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

test.describe('TC-BRAIN 大脑页', () => {
  test('BRAIN-01/02 导航可达且面板渲染', async ({ page }) => {
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '大脑' }).first().click()
    await expect(page).toHaveURL(/\/brain/)
    await expect(page.locator('[data-testid="brain-page"]')).toBeVisible()
    await expect(page.locator('.brain-status-panel')).toBeVisible()
    await expect(page.locator('.brain-run-list')).toBeVisible()
    await expect(page.locator('.page-title')).toHaveText('BrainLoop 观察台')
  })

  test('BRAIN-03 只读：仅发起 GET 请求', async ({ page }) => {
    const postUrls: string[] = []
    await page.route('**/*', (route) => {
      if (route.request().method() !== 'GET' && route.request().url().includes('/brain/')) {
        postUrls.push(route.request().url())
      }
      route.continue()
    })
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '大脑' }).first().click()
    await expect(page.locator('.brain-status-panel')).toBeVisible()
    await page.waitForTimeout(1500)
    expect(postUrls).toEqual([])
  })

  test('BRAIN-05 暂停自动刷新', async ({ page }) => {
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '大脑' }).first().click()
    const toggle = page.locator('[data-testid="brain-autorefresh-toggle"]')
    await expect(toggle).toContainText('自动刷新中')
    await toggle.click()
    await expect(toggle).toContainText('自动刷新已暂停')
    // 暂停后状态面板仍然可见（数据保留）
    await expect(page.locator('.brain-status-panel')).toBeVisible()
    await toggle.click()
    await expect(toggle).toContainText('自动刷新中')
  })

  test('BRAIN-04 run 列表交互（有记录时点详情）', async ({ page }) => {
    await page.route('**/brain/state', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          life_state: { life_loop_status: 'idle', current_activity: 'rest', energy: 0.9, mood: { label: '平静' } },
          scheduler_running: true,
        }),
      })
    )
    await page.route('**/brain/runs/recent*', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          runs: [{ run_id: 'run-e2e-001', mode: 'normal', selected_activity: 'test', started_at: '2026-09-01T10:00:00', cycle_count: 3 }],
        }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '大脑' }).first().click()
    await expect(page.locator('.brl-item')).toHaveCount(1)
    await expect(page.locator('.brl-mode')).toHaveText('normal')
    await page.locator('.brl-item').first().click()
    // 详情请求发出且面板存在（无详情数据时面板隐藏或显示空态）
    await expect(page.locator('.brain-run-list')).toBeVisible()
  })
})

test.describe('TC-GATE Gate 页', () => {
  test('GATE-01/03 列表渲染与状态显示', async ({ page }) => {
    await page.route('**/gate/config', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ bot_id: 'e2e-bot', has_secret: true, status: 'stopped', connected: false }) })
    )
    await page.route('**/gate/status', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'stopped', connected: false }) })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: 'Gate' }).first().click()
    await expect(page).toHaveURL(/\/gate/)
    await expect(page.locator('.gate-page')).toBeVisible()
    await expect(page.locator('.page-title')).toContainText('Gate')
    // 连接状态卡片
    await expect(page.locator('.card-row', { hasText: '连接状态' })).toBeVisible()
    await expect(page.locator('.status-text')).toHaveText('未连接')
    await expect(page.locator('.card-row', { hasText: '当前机器人' })).toContainText('e2e-bot')
    // 凭证配置卡片
    await expect(page.locator('.card-title', { hasText: '机器人凭证配置' })).toBeVisible()
  })

  test('GATE-02 启动连接按钮状态正确（未配置时禁用）', async ({ page }) => {
    await page.route('**/gate/config', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ bot_id: '', has_secret: false, status: 'stopped', connected: false }) })
    )
    await page.route('**/gate/status', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'stopped', connected: false }) })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: 'Gate' }).first().click()
    await expect(page.locator('.btn-primary', { hasText: '启动连接' })).toBeVisible()
    await expect(page.locator('.btn-primary', { hasText: '启动连接' })).toBeDisabled()
    await expect(page.locator('.card-value')).toHaveText('未配置')
  })
})
