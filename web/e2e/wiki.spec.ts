import { test, expect } from '@playwright/test'

test.describe('Wiki View', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/wiki', { waitUntil: 'networkidle' })
  })

  test('页面标题', async ({ page }) => {
    await expect(page.locator('.wiki-title')).toHaveText('Wiki 知识库')
  })

  test('文件列表区域', async ({ page }) => {
    await expect(page.locator('.file-section')).toBeVisible()
    await expect(page.locator('.fs-title')).toHaveText('文件列表')
  })

  test('侧边栏Tab切换 - 统计', async ({ page }) => {
    await page.locator('.side-tab-btn:has-text("统计")').click()
    await expect(page.locator('.wscard').first()).toBeVisible()
    await expect(page.locator('.wsc-label').first()).toHaveText('文件数')
  })

  test('侧边栏Tab切换 - 操作', async ({ page }) => {
    await page.locator('.side-tab-btn:has-text("操作")').click()
    const opsBtn = page.locator('.ops-btn')
    await expect(opsBtn).toBeVisible()
    await expect(opsBtn.locator('.ops-text')).toHaveText('重建索引')
  })

  test('侧边栏Tab切换 - 设置', async ({ page }) => {
    await page.locator('.side-tab-btn:has-text("设置")').click()
    await expect(page.locator('.form-label').first()).toHaveText('Wiki 目录')
    await expect(page.locator('.btn-save')).toHaveText('保存设置')
  })

  test('文件表格表头可点击排序', async ({ page }) => {
    const thFilename = page.locator('th:has-text("文件名")')
    const thSize = page.locator('th:has-text("大小")')
    const thModified = page.locator('th:has-text("修改时间")')
    await expect(thFilename).toBeVisible()
    await expect(thSize).toBeVisible()
    await expect(thModified).toBeVisible()
    await thFilename.click()
  })

  test('设置表单输入', async ({ page }) => {
    await page.locator('.side-tab-btn:has-text("设置")').click()
    const wikiDirInput = page.locator('.form-input').first()
    await wikiDirInput.fill('test_wiki')
    await expect(wikiDirInput).toHaveValue('test_wiki')
  })
})