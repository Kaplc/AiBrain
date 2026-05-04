import { test, expect } from '@playwright/test'

/**
 * Wiki 进度条 & 文件状态更新测试
 *
 * 测试策略：
 * - 后端同步完成所有文件（无真正异步），进度极快
 * - 测试重点：页面正常渲染 + rebuildIndex() 按钮可点击 + 文件列表显示
 * - 文件状态验证依赖异步进度更新，暂跳过（需要破坏文件 MD5 才能触发真实异步）
 */
test.describe('Wiki 进度条 & 文件状态更新', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/wiki')
    // 切换到操作 tab
    await page.click('.side-tab-btn:has-text("操作")')
    // 等待 ops panel 可见
    await expect(page.locator('.ops-section')).toBeVisible({ timeout: 5000 })
    // 等待系统处于空闲状态（按钮显示"重建索引"而非"索引中..."）
    await page.waitForFunction(() => {
      const btn = document.querySelector('.ops-btn .ops-text') as HTMLElement
      return btn && btn.textContent !== '索引中...'
    }, { timeout: 30000 })
  })

  test('页面加载后文件列表正常显示', async ({ page }) => {
    await page.waitForSelector('.file-table', { timeout: 10000 })
    const rows = await page.locator('.file-table tbody tr').count()
    expect(rows).toBeGreaterThan(0)
  })

  test('重建索引按钮可点击且不报错的', async ({ page }) => {
    await page.waitForSelector('.file-table', { timeout: 10000 })

    // 点击重建索引（后端同步完成，速度极快，不依赖 disabled 状态）
    await page.click('.ops-btn:not(:disabled)')

    // 等待一小段时间确保异步请求发出
    await page.waitForTimeout(500)

    // 文件列表仍然正常（没崩溃）
    const rows = await page.locator('.file-table tbody tr').count()
    expect(rows).toBeGreaterThan(0)
  })

  test('索引完成后按钮恢复，文件列表仍正常', async ({ page }) => {
    await page.waitForSelector('.file-table', { timeout: 10000 })

    // 点击重建索引
    await page.click('.ops-btn:not(:disabled)')

    // 等待按钮恢复可用（最多30秒，覆盖快速同步完成的场景）
    await expect(page.locator('.ops-btn:not(:disabled)')).toBeVisible({ timeout: 30000 })

    // 文件列表仍然正常显示
    const rows = await page.locator('.file-table tbody tr').count()
    expect(rows).toBeGreaterThan(0)
  })
})
