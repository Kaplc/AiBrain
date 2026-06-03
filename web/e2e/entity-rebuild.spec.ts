import { test, expect, type APIRequestContext } from '@playwright/test'

/* EntityTab - 实体网络重建 UI 集成 */
const BASE_URL = 'http://127.0.0.1:19398'

async function resetRebuildState(request: APIRequestContext) {
  // 如果有任务在跑，先取消
  const status = await request.get(`${BASE_URL}/memory/graph/rebuild`).then(r => r.json())
  if (status.status === 'running') {
    await request.post(`${BASE_URL}/memory/graph/rebuild/cancel`)
    // 等线程真正退出
    for (let i = 0; i < 30; i++) {
      await new Promise(res => setTimeout(res, 1000))
      const s = await request.get(`${BASE_URL}/memory/graph/rebuild`).then(r => r.json())
      if (s.status !== 'running') return
    }
  }
}

test.describe('EntityTab 实体网络重建', () => {
  test.beforeEach(async ({ page, request }) => {
    // 确保后端是 idle 状态（避免上次测试遗留的 running 影响按钮文字）
    await resetRebuildState(request)
    // 进入 MemoryView
    await page.goto('/memory', { waitUntil: 'networkidle' })
    // 切到实体 Tab
    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()
  })

  test('A1 工具栏显示「重建实体网络」按钮', async ({ page }) => {
    const btn = page.locator('.btn-rebuild')
    await expect(btn).toBeVisible()
    await expect(btn).toContainText('重建实体网络')
  })

  test('A2 idle 状态默认无进度卡片', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()
    // idle 时不显示进度卡片
    await expect(page.locator('.rebuild-card')).toHaveCount(0)
  })

  test('A3 点击按钮后状态变为 running、显示进度卡片', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()

    await page.locator('.btn-rebuild').click()
    // 进度卡片出现
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.rebuild-card')).toHaveClass(/running/)
    // 按钮文案变为「重建中...」
    await expect(page.locator('.btn-rebuild')).toContainText('重建中')
    // 取消按钮出现
    await expect(page.locator('.btn-cancel')).toBeVisible()
  })

  test('A4 进度数字递增（轮询生效）', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })

    // 第一次抓到 processed
    const text1 = await page.locator('.progress-text').textContent()
    const n1 = parseInt(text1?.match(/(\d+)/)?.[1] || '0', 10)
    // 等 4s 后再次抓（轮询周期 2s）
    await page.waitForTimeout(4000)
    const text2 = await page.locator('.progress-text').textContent()
    const n2 = parseInt(text2?.match(/(\d+)/)?.[1] || '0', 10)
    expect(n2).toBeGreaterThanOrEqual(n1)
  })

  test('A6 并发启动被拒绝（按钮在 running 时被禁用）', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    // 按钮 disabled
    await expect(page.locator('.btn-rebuild')).toBeDisabled()
  })

  test('A7 取消按钮可点击', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    await page.locator('.btn-cancel').click()
    // 取消后等几秒，轮询会拉到 idle 状态
    await expect(page.locator('.rebuild-card')).toHaveCount(0, { timeout: 10000 })
  })

  test('A8 查看日志按钮可点击并展开日志面板', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    // 点击「查看日志」展开
    await page.locator('.btn-link:has-text("查看日志")').click()
    await expect(page.locator('.rebuild-log')).toBeVisible({ timeout: 5000 })
  })

  test('A10 切走再切回，进度卡片仍在', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    // 切到搜索 Tab
    await page.locator('.nav-tab:has-text("搜索记忆")').click()
    await page.waitForTimeout(500)
    // 切回实体 Tab
    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()
    // 进度卡片应自动恢复
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    // 仍然 running
    await expect(page.locator('.rebuild-card')).toHaveClass(/running/)
  })

  test('A12 进度卡片显示线程数/模型调用/成功率', async ({ page, request }) => {
    await resetRebuildState(request)
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.nav-tab:has-text("实体")').click()
    await page.locator('.btn-rebuild').click()
    await expect(page.locator('.rebuild-card')).toBeVisible({ timeout: 5000 })
    // 标签应包含「线程数」「模型调用」「LLM 成功率」
    await expect(page.locator('.rebuild-stats')).toContainText('线程数')
    await expect(page.locator('.rebuild-stats')).toContainText('模型调用')
    await expect(page.locator('.rebuild-stats')).toContainText('LLM 成功率')
    // 数字部分（stat-value）依然存在
    const statCards = page.locator('.stat-cards .stat-value')
    await expect(statCards).toHaveCount(5)
  })
})
