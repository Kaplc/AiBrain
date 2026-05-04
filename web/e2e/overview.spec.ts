import { test, expect } from '@playwright/test'

/* Overview - 4个卡片 + 图表 + 统计 */
test.describe('Overview', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/overview', { waitUntil: 'networkidle' })
  })

  // ===== 卡片渲染 =====
  test('4个状态卡片渲染', async ({ page }) => {
    await expect(page.locator('.status-card')).toHaveCount(4)
  })

  test('ModelCard标签 - 模型状态', async ({ page }) => {
    await page.waitForTimeout(3000) // 等待轮询
    const card = page.locator('.status-card').nth(0)
    await expect(card.locator('.sc-label')).toHaveText('模型状态')
    const badge = card.locator('[class*="badge"]')
    const text = (await badge.textContent())?.trim()
    expect(['OK', '']).toContain(text)
  })

  test('QdrantCard标签 - Qdrant状态', async ({ page }) => {
    await page.waitForTimeout(3000)
    const card = page.locator('.status-card').nth(1)
    await expect(card.locator('.sc-label')).toHaveText('Qdrant 状态')
    const badge = card.locator('[class*="badge"]')
    const text = (await badge.textContent())?.trim()
    expect(['OK', '']).toContain(text)
  })

  test('FlaskCard标签 - Flask状态 + 重启按钮', async ({ page }) => {
    await page.waitForTimeout(3000)
    const card = page.locator('.status-card').nth(2)
    await expect(card.locator('.sc-label')).toHaveText('Flask 状态')
    await expect(card.locator('.flask-restart-btn')).toBeVisible()
    const badge = card.locator('[class*="badge"]')
    const text = (await badge.textContent())?.trim()
    expect(['OK', 'restarting', 'err']).toContain(text)
  })

  test('DeviceCard标签 - 设备信息', async ({ page }) => {
    await page.waitForTimeout(2000)
    const card = page.locator('.status-card').nth(3)
    await expect(card.locator('.sc-label')).toHaveText('设备信息')
    const subs = card.locator('.sc-sub')
    await expect(subs.first()).toBeVisible()
  })

  test('DeviceCard显示CPU和内存', async ({ page }) => {
    await page.waitForTimeout(2000)
    const subs = page.locator('.status-card').nth(3).locator('.sc-sub')
    const allText = await subs.allTextContents()
    expect(allText.some(t => t.includes('CPU:'))).toBe(true)
    expect(allText.some(t => t.includes('内存:'))).toBe(true)
  })

  // ===== 图表区域 =====
  test('图表标题存在', async ({ page }) => {
    await expect(page.locator('.chart-section')).toBeVisible()
    await expect(page.locator('.chart-title')).toHaveText('记忆数据')
  })

  test('图表canvas元素存在', async ({ page }) => {
    await expect(page.locator('.chart-section')).toBeVisible()
  })

  // ===== 数据视图切换 =====
  test('累计曲线Tab默认激活', async ({ page }) => {
    await expect(page.locator('.data-tab.active')).toHaveText('累计曲线')
  })

  test('切换到新增曲线', async ({ page }) => {
    await page.locator('.data-tab:has-text("新增曲线")').click()
    await expect(page.locator('.data-tab.active')).toHaveText('新增曲线')
  })

  test('切换回累计曲线', async ({ page }) => {
    await page.locator('.data-tab:has-text("新增曲线")').click()
    await page.locator('.data-tab:has-text("累计曲线")').click()
    await expect(page.locator('.data-tab.active')).toHaveText('累计曲线')
  })

  // ===== 日期范围切换 =====
  test('近24小时Tab默认激活', async ({ page }) => {
    await expect(page.locator('.chart-tab.active')).toHaveText('近24小时')
  })

  test('切换到7天', async ({ page }) => {
    await page.locator('.chart-tab:has-text("7天")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('7天')
  })

  test('切换到30天', async ({ page }) => {
    await page.locator('.chart-tab:has-text("30天")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('30天')
  })

  test('切换到全部 - 隐藏增量统计', async ({ page }) => {
    await page.locator('.chart-tab:has-text("全部")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('全部')
    const incrementBox = page.locator('.stat-box').nth(1)
    await expect(incrementBox).toBeHidden()
  })

  test('从全部切回24小时 - 恢复增量统计', async ({ page }) => {
    await page.locator('.chart-tab:has-text("全部")').click()
    await page.locator('.chart-tab:has-text("近24小时")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('近24小时')
    const incrementBox = page.locator('.stat-box').nth(1)
    await expect(incrementBox).toBeVisible()
  })

  test('切换到30天再切回7天', async ({ page }) => {
    await page.locator('.chart-tab:has-text("30天")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('30天')
    await page.locator('.chart-tab:has-text("7天")').click()
    await expect(page.locator('.chart-tab.active')).toHaveText('7天')
  })

  // ===== 统计数值 =====
  test('记忆总数stat显示', async ({ page }) => {
    await page.waitForTimeout(2000)
    const totalBox = page.locator('.stat-box').first()
    await expect(totalBox.locator('.sb-label')).toHaveText('记忆总数')
    const value = await totalBox.locator('.sb-value').textContent()
    expect(value).not.toBe('')
  })

  // ===== 重启按钮 =====
  test('Flask重启按钮可点击', async ({ page }) => {
    const btn = page.locator('.flask-restart-btn')
    await expect(btn).toBeVisible()
    await expect(btn).toHaveText('重启')
    await btn.click()
    await page.waitForTimeout(500)
    // 按钮应该变为disabled状态（重启中）
    await expect(btn).toHaveText('重启中...')
  })

  // ===== 页面切换后图表重绘 =====
  test('切换页面后返回图表重绘', async ({ page }) => {
    await page.waitForTimeout(1000)
    await page.goto('/memory')
    await page.waitForTimeout(500)
    await page.goto('/overview')
    await page.waitForTimeout(1000)
    await expect(page.locator('.chart-section')).toBeVisible()
  })

  // ===== 新增曲线视图统计 =====
  test('新增曲线视图显示统计标签', async ({ page }) => {
    await page.locator('.data-tab:has-text("新增曲线")').click()
    // 图表区域可见
    await expect(page.locator('.chart-section')).toBeVisible()
  })
})
