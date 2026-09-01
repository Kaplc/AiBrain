/* 总览页（TC-OV）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

test.describe('TC-OV 总览页', () => {
  test('OV-01 状态卡片渲染（首行4张 + Token/余额卡）', async ({ page }) => {
    await waitForApp(page)
    // 首行 4 张状态卡
    const firstRow = page.locator('.overview-row').first()
    await expect(firstRow.locator('.status-card')).toHaveCount(4)
    const labels = await page.locator('.status-card .sc-label').allTextContents()
    expect(labels).toContain('模型状态')
    expect(labels).toContain('Qdrant 状态')
    expect(labels).toContain('Flask 状态')
    expect(labels).toContain('设备信息')
    // TokenCard / BalanceCard 也用 status-card 类
    await expect(page.locator('.status-card', { hasText: 'LLM Token 用量' })).toBeVisible()
  })

  test('OV-02 ModelCard 模型就绪（后端已预热）', async ({ page }) => {
    await waitForApp(page)
    const model = await page.evaluate(() => fetch('/overview/model').then((r) => r.json()))
    test.skip(!model.loaded, '后端模型未完成预热')
    const card = page.locator('.status-card', { hasText: '模型状态' })
    await expect(card.locator('.sc-sub')).toHaveText('模型就绪', { timeout: 10000 })
    await expect(card.locator('.badge-ok')).toBeVisible()
  })

  test('OV-03 QdrantCard 就绪状态', async ({ page }) => {
    await waitForApp(page)
    const qdrant = await page.evaluate(() => fetch('/overview/qdrant').then((r) => r.json()))
    test.skip(!qdrant.ready, 'Qdrant 未就绪')
    const card = page.locator('.status-card', { hasText: 'Qdrant 状态' })
    await expect(card.locator('.badge-ok')).toBeVisible({ timeout: 10000 })
    await expect(card.locator('.sc-sub')).toContainText(`${qdrant.host}:${qdrant.port}`)
  })

  test('OV-04 FlaskCard 重启按钮可见', async ({ page }) => {
    await waitForApp(page)
    const card = page.locator('.status-card', { hasText: 'Flask 状态' })
    await expect(card.locator('.flask-restart-btn')).toBeVisible()
    await expect(card.locator('.flask-restart-btn')).toHaveText('重启')
  })

  test('OV-05 DeviceCard 含 CPU 与内存子项', async ({ page }) => {
    await waitForApp(page)
    const card = page.locator('.status-card', { hasText: '设备信息' })
    await expect(card.locator('.sc-sub', { hasText: 'CPU:' })).toBeVisible({ timeout: 10000 })
    await expect(card.locator('.sc-sub', { hasText: '内存:' })).toBeVisible()
  })

  test('OV-09 记忆总数统计', async ({ page }) => {
    await waitForApp(page)
    const cnt = await page.evaluate(() => fetch('/memory/count').then((r) => r.json()))
    expect(cnt.count).toBeGreaterThanOrEqual(0)
  })

  test('OV-12 BalanceCard 与 TokenCard 渲染', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.token-card-wide .sc-label')).toContainText('LLM Token 用量')
    // TokenCard 3 个时间范围 tab
    await expect(page.locator('.token-card-wide .chart-tab')).toHaveCount(3)
    // BalanceCard 存在（未配 Key 时显示"请在 LLM 设置中配置 API Key"）
    await expect(page.locator('.status-card', { hasText: 'DeepSeek 余额' })).toBeVisible({ timeout: 15000 })
  })

  test('OV-12b TokenCard 图表 canvas 渲染', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.token-card-wide .chart-box canvas').first()).toBeVisible({ timeout: 15000 })
  })
})
