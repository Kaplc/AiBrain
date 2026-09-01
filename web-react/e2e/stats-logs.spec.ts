/* 用量页（TC-STATS）+ 日志页（TC-LOGS）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

test.describe('TC-STATS 用量页', () => {
  test('STATS-01 图表渲染与余额卡', async ({ page }) => {
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '用量' }).first().click()
    await expect(page).toHaveURL(/\/stats/)
    await expect(page.locator('.stats-page')).toBeVisible()
    await expect(page.locator('.page-title')).toHaveText('用量')
    // Token 用量图表 canvas
    await expect(page.locator('.token-card .chart-box canvas').first()).toBeVisible({ timeout: 15000 })
    // DeepSeek 余额卡
    await expect(page.locator('.stat-card', { hasText: 'DeepSeek 余额' })).toBeVisible({ timeout: 15000 })
  })

  test('STATS-02 时间范围切换后图表刷新', async ({ page }) => {
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '用量' }).first().click()
    await expect(page.locator('.token-card .chart-tab')).toHaveCount(3)
    await expect(page.locator('.token-card .chart-tab.active')).toHaveText('24h')
    await page.locator('.token-card .chart-tab', { hasText: '7d' }).click()
    await expect(page.locator('.token-card .chart-tab.active')).toHaveText('7d')
    await page.locator('.token-card .chart-tab', { hasText: '30d' }).click()
    await expect(page.locator('.token-card .chart-tab.active')).toHaveText('30d')
    // 统计行仍然渲染
    await expect(page.locator('.token-card .sb-l', { hasText: '消耗' })).toBeVisible()
  })
})

test.describe('TC-LOGS 日志页', () => {
  test('LOGS-01/02 标题与输出区域', async ({ page }) => {
    await page.route('**/logs/api*', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ lines: ['[2026-09-01 10:00:00] [INFO] e2e log line', '[2026-09-01 10:00:01] [ERROR] e2e error line'], file: 'flask.log', total_relevant: 2, returned: 2 }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '日志' }).first().click()
    await expect(page).toHaveURL(/\/logs/)
    await expect(page.locator('.logs-title')).toHaveText('日志')
    // 三个日志源 Tab
    await expect(page.locator('.log-tab')).toHaveCount(3)
    await expect(page.locator('.log-tab.active')).toContainText('系统日志')
    // 日志行渲染与着色
    await expect(page.locator('.log-wrap')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('.log-level-info').first()).toBeVisible()
    await expect(page.locator('.log-level-error').first()).toBeVisible()
    // 元信息
    await expect(page.locator('.ft-meta')).toContainText('共 2 条')
  })

  test('LOGS-03 刷新按钮点击后重新加载', async ({ page }) => {
    let calls = 0
    await page.route('**/logs/api*', (route) => {
      calls++
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ lines: ['[2026-09-01 10:00:00] [INFO] refresh test ' + calls], file: 'flask.log', total_relevant: 1, returned: 1 }),
      })
    })
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '日志' }).first().click()
    await expect(page.locator('.log-wrap')).toBeVisible({ timeout: 10000 })
    const before = calls
    await page.locator('.btn-secondary', { hasText: '刷新' }).click()
    await expect(page.locator('.log-wrap')).toContainText('refresh test ' + (before + 1), { timeout: 10000 })
  })

  test('LOGS-04 自动滚动到底部', async ({ page }) => {
    const lines: string[] = []
    for (let i = 0; i < 200; i++) lines.push(`[2026-09-01 10:00:00] [INFO] line ${i}`)
    await page.route('**/logs/api*', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ lines, file: 'flask.log', total_relevant: 200, returned: 200 }) })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '日志' }).first().click()
    await expect(page.locator('.log-wrap')).toBeVisible({ timeout: 10000 })
    await expect.poll(async () => {
      return page.evaluate(() => {
        const el = document.querySelector('.log-wrap') as HTMLElement | null
        if (!el) return 0
        return el.scrollHeight - el.scrollTop - el.clientHeight
      })
    }).toBeLessThanOrEqual(30)
  })

  test('LOGS-05 切换日志源 Tab', async ({ page }) => {
    await page.route('**/logs/api*', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ lines: ['[2026-09-01] [INFO] src'], file: 'x.log', total_relevant: 1, returned: 1 }) })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '日志' }).first().click()
    await expect(page.locator('.log-tab')).toHaveCount(3)
    await page.locator('.log-tab', { hasText: 'Mem0 日志' }).click()
    await expect(page.locator('.log-tab.active')).toContainText('Mem0 日志')
    await page.locator('.log-tab', { hasText: '语义模型' }).click()
    await expect(page.locator('.log-tab.active')).toContainText('语义模型')
  })
})
