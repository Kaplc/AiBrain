import { test, expect } from '@playwright/test'

test.describe('Logs View', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/logs', { waitUntil: 'networkidle' })
  })

  test('页面标题', async ({ page }) => {
    await expect(page.locator('.logs-title')).toHaveText('日志')
  })

  test('日志输出区域', async ({ page }) => {
    await expect(page.locator('.log-wrap')).toBeVisible()
  })

  test('刷新按钮', async ({ page }) => {
    const refreshBtn = page.locator('.log-header .btn-action')
    await expect(refreshBtn).toBeVisible()
    await expect(refreshBtn).toHaveText('刷新')
  })
})