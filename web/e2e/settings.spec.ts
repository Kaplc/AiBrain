import { test, expect } from '@playwright/test'

/* Settings - 动态Tab (v-if 条件渲染，激活的tab才在DOM中) */
test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings', { waitUntil: 'networkidle' })
  })

  test('页面标题', async ({ page }) => {
    await expect(page.locator('.settings-title')).toHaveText('设置')
  })

  test('三个Tab按钮存在', async ({ page }) => {
    await expect(page.locator('.tab-btn')).toHaveCount(3)
    await expect(page.locator('.tab-btn:has-text("模型")')).toBeVisible()
    await expect(page.locator('.tab-btn:has-text("mem0.json")')).toBeVisible()
    await expect(page.locator('.tab-btn:has-text("wiki.json")')).toBeVisible()
  })

  test('模型Tab - 默认显示且唯一', async ({ page }) => {
    // 模型Tab默认激活，应该在DOM中
    await expect(page.locator('.model-select')).toBeVisible()
    await expect(page.locator('.device-select')).toBeVisible()
  })

  test('模型Tab - 设备选项', async ({ page }) => {
    await expect(page.locator('.device-select option[value="cpu"]')).toHaveText('CPU')
    await expect(page.locator('.device-select option[value="gpu"]')).toHaveText('GPU')
    await expect(page.locator('.device-select option[value="auto"]')).toHaveText('自动')
  })

  test('模型Tab - 重置按钮', async ({ page }) => {
    // 使用.btn-secondary 定位（模型Tab激活状态下唯一）
    await expect(page.locator('.btn-secondary').first()).toHaveText('重置')
  })

  test('模型Tab - 保存按钮', async ({ page }) => {
    await expect(page.locator('.btn-primary').first()).toHaveText('保存')
  })

  test('模型Tab - 选择CPU', async ({ page }) => {
    await page.locator('.device-select').selectOption('cpu')
    await expect(page.locator('.device-select')).toHaveValue('cpu')
  })

  test('模型Tab - 选择GPU', async ({ page }) => {
    await page.locator('.device-select').selectOption('gpu')
    await expect(page.locator('.device-select')).toHaveValue('gpu')
  })

  test('模型Tab - GPU信息区域', async ({ page }) => {
    await page.waitForTimeout(3000)
    await expect(page.locator('.gpu-info')).toBeVisible()
  })

  test('Tab切换mem0 - mem0 Tab渲染且模型Tab消失', async ({ page }) => {
    await page.locator('.tab-btn:has-text("mem0.json")').click()
    // mem0 Tab内容应该在DOM中
    await expect(page.locator('.config-form')).toBeVisible()
    // 模型Tab相关元素应该不在DOM中
    await expect(page.locator('.model-select')).not.toBeVisible()
  })

  test('Tab切换wiki - wiki Tab渲染', async ({ page }) => {
    await page.locator('.tab-btn:has-text("wiki.json")').click()
    await expect(page.locator('.config-form')).toBeVisible()
  })

  test('Tab切换 - mem0后切回模型', async ({ page }) => {
    await page.locator('.tab-btn:has-text("mem0.json")').click()
    await page.locator('.tab-btn:has-text("模型")').click()
    await expect(page.locator('.model-select')).toBeVisible()
    await expect(page.locator('.device-select')).toBeVisible()
  })

  test('Tab切换 - wiki后切回模型', async ({ page }) => {
    await page.locator('.tab-btn:has-text("wiki.json")').click()
    await page.locator('.tab-btn:has-text("模型")').click()
    await expect(page.locator('.model-select')).toBeVisible()
  })

  test('mem0 Tab - 保存和恢复默认按钮', async ({ page }) => {
    await page.locator('.tab-btn:has-text("mem0.json")').click()
    // 因为v-if，mem0 Tab激活后才在DOM中
    const btns = page.locator('.btn')
    await expect(btns.filter({ hasText: '保存' })).toBeVisible()
    await expect(btns.filter({ hasText: '恢复默认' })).toBeVisible()
  })

  test('wiki Tab - 保存和恢复默认按钮', async ({ page }) => {
    await page.locator('.tab-btn:has-text("wiki.json")').click()
    const btns = page.locator('.btn')
    await expect(btns.filter({ hasText: '保存' })).toBeVisible()
    await expect(btns.filter({ hasText: '恢复默认' })).toBeVisible()
  })
})
