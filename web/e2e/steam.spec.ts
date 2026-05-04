import { test, expect } from '@playwright/test'

test.describe('Stream View', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/stream', { waitUntil: 'networkidle' })
  })

  test('页面标题和计数', async ({ page }) => {
    await expect(page.locator('.steam-title')).toHaveText('记忆流')
    await expect(page.locator('.steam-count')).toBeVisible()
  })

  test('两列布局', async ({ page }) => {
    const columns = page.locator('.steam-column')
    await expect(columns).toHaveCount(2)
    await expect(page.locator('.steam-column-header').first()).toContainText('MCP调用')
    await expect(page.locator('.steam-column-header').last()).toContainText('查询记忆')
  })

  test('MCP调用列表', async ({ page }) => {
    const list = page.locator('.steam-column').first().locator('.steam-list')
    await expect(list).toBeVisible()
  })

  test('查询记忆列表', async ({ page }) => {
    const list = page.locator('.steam-column').last().locator('.steam-list')
    await expect(list).toBeVisible()
  })
})