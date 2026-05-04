import { test, expect } from '@playwright/test'

/* Memory - 搜索/保存/整理 三个Tab */
test.describe('Memory', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
  })

  test('三个NavTab渲染', async ({ page }) => {
    await expect(page.locator('.nav-tab:has-text("搜索记忆")')).toBeVisible()
    await expect(page.locator('.nav-tab:has-text("保存记忆")')).toBeVisible()
    await expect(page.locator('.nav-tab:has-text("整理记忆")')).toBeVisible()
  })

  test('搜索记忆Tab - 搜索框', async ({ page }) => {
    await expect(page.locator('.search-bar input')).toBeVisible()
    await expect(page.locator('.search-bar input')).toHaveAttribute('placeholder', '搜索相关记忆...')
  })

  test('搜索记忆Tab - 搜索按钮', async ({ page }) => {
    const searchBtn = page.locator('.search-bar .btn-primary')
    await expect(searchBtn).toBeVisible()
  })

  test('保存记忆Tab - 切换', async ({ page }) => {
    await page.locator('.nav-tab:has-text("保存记忆")').click()
    await expect(page.locator('.nav-tab:has-text("保存记忆")')).toHaveClass(/active/)
    await expect(page.locator('.store-area textarea')).toBeVisible()
    await expect(page.locator('.store-area .btn-primary')).toHaveText('保存记忆')
  })

  test('保存记忆Tab - 输入框可输入', async ({ page }) => {
    await page.locator('.nav-tab:has-text("保存记忆")').click()
    const textarea = page.locator('.store-area textarea')
    await textarea.fill('测试记忆内容')
    await expect(textarea).toHaveValue('测试记忆内容')
  })

  test('保存记忆Tab - 保存按钮可点击', async ({ page }) => {
    await page.locator('.nav-tab:has-text("保存记忆")').click()
    const saveBtn = page.locator('.store-area .btn-primary')
    await expect(saveBtn).toBeEnabled()
  })

  test('整理记忆Tab - 切换', async ({ page }) => {
    await page.locator('.nav-tab:has-text("整理记忆")').click()
    await expect(page.locator('.nav-tab:has-text("整理记忆")')).toHaveClass(/active/)
  })

  test('整理记忆Tab - 去重选择框', async ({ page }) => {
    await page.locator('.nav-tab:has-text("整理记忆")').click()
    await expect(page.locator('.organize-select')).toBeVisible()
  })

  test('整理记忆Tab - 开始分析按钮', async ({ page }) => {
    await page.locator('.nav-tab:has-text("整理记忆")').click()
    const btn = page.locator('.btn-accent')
    await expect(btn).toHaveText('开始分析')
  })

  test('记忆总数显示', async ({ page }) => {
    await expect(page.locator('.stat-label')).toHaveText('条记忆')
    const text = await page.locator('.stat-value').textContent()
    expect(text).not.toBeNull()
  })

  test('搜索结果区域存在', async ({ page }) => {
    // 搜索Tab激活时，搜索结果列表在 search-bar 同级区域
    await expect(page.locator('.search-bar')).toBeVisible()
  })

  test('切换Tab后内容变化', async ({ page }) => {
    // 默认是搜索Tab
    await expect(page.locator('.search-bar')).toBeVisible()
    // 切换到保存Tab
    await page.locator('.nav-tab:has-text("保存记忆")').click()
    await expect(page.locator('.store-area')).toBeVisible()
    // 切换到整理Tab
    await page.locator('.nav-tab:has-text("整理记忆")').click()
    await expect(page.locator('.organize-select')).toBeVisible()
    // 切回搜索Tab
    await page.locator('.nav-tab:has-text("搜索记忆")').click()
    await expect(page.locator('.search-bar')).toBeVisible()
  })
})
