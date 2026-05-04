import { test, expect } from '@playwright/test'

/* 全局导航和布局 */
test.describe('Navigation', () => {
  test('侧边栏有6个导航项', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await expect(page.locator('.nav-item')).toHaveCount(6)
  })

  test('默认加载总览页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await expect(page).toHaveURL(/\/overview/)
    await expect(page.locator('.nav-item.active .nav-label')).toHaveText('总览')
  })

  test('点击导航到记忆页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("记忆")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/memory/)
    await expect(page.locator('.nav-item.active .nav-label')).toHaveText('记忆')
  })

  test('点击导航到流页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("流")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/stream/)
  })

  test('点击导航到Wiki页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("Wiki")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/wiki/)
  })

  test('点击导航到日志页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("日志")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/logs/)
  })

  test('点击导航到设置页面', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.locator('.nav-sidebar .nav-item:has-text("设置")').click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(/\/settings/)
  })

  test('状态栏存在', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await expect(page.locator('.statusbar')).toBeVisible()
  })

  test('控制台快捷键~显示', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.keyboard.press('`')
    await page.waitForTimeout(300)
    await expect(page.locator('.console-wrap')).toBeVisible()
  })

  test('控制台可关闭', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.keyboard.press('`')
    await page.waitForTimeout(300)
    await expect(page.locator('.console-wrap')).toBeVisible()
    await page.locator('.btn-close').click()
    await page.waitForTimeout(300)
    await expect(page.locator('.console-wrap')).not.toBeVisible()
  })
})
