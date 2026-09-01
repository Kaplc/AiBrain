/* 记忆页（TC-MEM，7 Tab）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

const TABS = ['搜索记忆', '保存记忆', '合并记忆', '记忆数据', '图谱', '实体', '⚙ 设置']

async function gotoMemory(page: import('@playwright/test').Page) {
  await waitForApp(page)
  await page.locator('.nav-item', { hasText: '记忆' }).first().click()
  await expect(page).toHaveURL(/\/memory/)
  await expect(page.locator('.nav-tab')).toHaveCount(7)
}

test.describe('TC-MEM 记忆页', () => {
  test('MEM-00 Tab 渲染与默认态', async ({ page }) => {
    await gotoMemory(page)
    for (const t of TABS) {
      await expect(page.locator('.nav-tab', { hasText: t })).toBeVisible()
    }
    await expect(page.locator('.nav-tab.active')).toHaveText('搜索记忆')
    // 记忆总数动画计数存在
    await expect(page.locator('.nav-stat .stat-value')).toBeVisible()
    await expect(page.locator('.nav-stat .stat-label')).toHaveText('条记忆')
  })

  test('MEM-TAB 快速遍历全部 Tab 不崩溃', async ({ page }) => {
    await gotoMemory(page)
    for (const t of TABS) {
      await page.locator('.nav-tab', { hasText: t }).click()
      await expect(page.locator('.nav-tab.active')).toHaveText(t)
    }
    // 随机顺序回切
    await page.locator('.nav-tab', { hasText: '图谱' }).click()
    await page.locator('.nav-tab', { hasText: '搜索记忆' }).click()
    await expect(page.locator('.nav-tab.active')).toHaveText('搜索记忆')
  })

  test.describe('搜索记忆 Tab', () => {
    test('MEM-S1 搜索框/按钮/历史开关可见', async ({ page }) => {
      await gotoMemory(page)
      await expect(page.locator('.search-input')).toBeVisible()
      await expect(page.locator('.search-input')).toHaveAttribute('placeholder', '输入关键词搜索记忆...')
      await expect(page.locator('.btn-accent', { hasText: '搜索' })).toBeVisible()
      await expect(page.locator('.search-history-wrap .btn-ghost')).toBeVisible()
    })

    test('MEM-S2 初始提示', async ({ page }) => {
      await gotoMemory(page)
      await expect(page.locator('.empty-text')).toHaveText('输入关键词开始搜索记忆')
    })

    test('MEM-S4 空输入不触发搜索', async ({ page }) => {
      await gotoMemory(page)
      let called = false
      await page.route('**/memory/search', (route) => { called = true; route.continue() })
      await page.locator('.btn-accent', { hasText: '搜索' }).click({ force: true })
      await page.waitForTimeout(500)
      expect(called).toBe(false)
    })

    test('MEM-S3 输入触发搜索并渲染结果或空状态', async ({ page }) => {
      await gotoMemory(page)
      const kw = 'e2e-test-记忆搜索-' + Date.now()
      await page.route('**/memory/search', async (route) => {
        const req = route.request().postDataJSON()
        if (req?.query === kw) {
          await route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({
              results: [
                { id: 'e2e-mem-0001', text: 'E2E 测试记忆 A', timestamp: '2026-09-01 12:00:00', score: 0.92, category: 'fact' },
                { id: 'e2e-mem-0002', text: 'E2E 测试记忆 B', timestamp: '2026-09-01 12:01:00' },
              ],
            }),
          })
        } else {
          await route.continue()
        }
      })
      await page.locator('.search-input').fill(kw)
      await page.keyboard.press('Enter')
      await expect(page.locator('.result-list .memory-item')).toHaveCount(2)
      const first = page.locator('.memory-item').first()
      await expect(first.locator('.mi-text')).toHaveText('E2E 测试记忆 A')
      await expect(first.locator('.mi-category')).toHaveText('事实')
      await expect(first.locator('.mi-score')).toHaveText('92.0%')
      await expect(first.locator('.mi-id')).toContainText('e2e-mem')
    })

    test('MEM-S6 空结果显示空状态文案', async ({ page }) => {
      await gotoMemory(page)
      const kw = 'e2e-empty-' + Date.now()
      await page.route('**/memory/search', async (route) => {
        const req = route.request().postDataJSON()
        if (req?.query === kw) {
          await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ results: [] }) })
        } else {
          await route.continue()
        }
      })
      await page.locator('.search-input').fill(kw)
      await page.keyboard.press('Enter')
      await expect(page.locator('.empty-text')).toHaveText('没有找到相关记忆')
    })

    test('MEM-S8 删除结果卡', async ({ page }) => {
      await gotoMemory(page)
      const kw = 'e2e-del-' + Date.now()
      let deleteCalled = false
      await page.route('**/memory/search', async (route) => {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ results: [{ id: 'del-target-01', text: '待删除记忆', timestamp: '2026-09-01 12:00:00' }] }),
        })
      })
      await page.route('**/memory/delete', async (route) => {
        deleteCalled = true
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: '删除成功' }) })
      })
      await page.locator('.search-input').fill(kw)
      await page.keyboard.press('Enter')
      await expect(page.locator('.memory-item')).toHaveCount(1)
      await page.locator('.memory-item .btn-del').click()
      await expect.poll(() => deleteCalled).toBe(true)
      await expect(page.locator('.memory-item')).toHaveCount(0)
    })

    test('MEM-S7 历史下拉打开与关闭', async ({ page }) => {
      // mock 必须在 SearchPanel 挂载（自动加载历史）之前注册
      await page.route('**/memory/search-history', (route) =>
        route.fulfill({ contentType: 'application/json', body: JSON.stringify({ history: [{ query: '历史问题1' }] }) })
      )
      await waitForApp(page)
      await page.locator('.nav-item', { hasText: '记忆' }).first().click()
      await expect(page.locator('.nav-tab')).toHaveCount(7)
      await page.locator('.search-history-wrap .btn-ghost').click()
      await expect(page.locator('.history-dropdown')).toBeVisible()
      await expect(page.locator('.history-item')).toHaveText('历史问题1')
      // 点击外部关闭
      await page.locator('.memory-nav').click()
      await expect(page.locator('.history-dropdown')).toHaveCount(0)
    })

    test('MEM-S9 搜索失败显示 error toast', async ({ page }) => {
      await gotoMemory(page)
      await page.route('**/memory/search', (route) => route.abort('failed'))
      await page.locator('.search-input').fill('e2e-fail')
      await page.keyboard.press('Enter')
      await expect(page.locator('.toast.error.show')).toBeVisible({ timeout: 10000 })
    })
  })

  test.describe('保存记忆 Tab', () => {
    test('MEM-ST1 保存成功 toast 且输入清空', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '保存记忆' }).click()
      const ta = page.locator('.store-textarea')
      await expect(ta).toBeVisible()
      await page.route('**/memory/store', (route) =>
        route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: '保存成功' }) })
      )
      await ta.fill('E2E 保存的记忆内容')
      await page.locator('.btn-accent', { hasText: '保存记忆' }).click()
      await expect(page.locator('.toast.show')).toBeVisible()
      await expect(ta).toHaveValue('')
    })
  })

  test.describe('合并记忆 Tab', () => {
    test('MEM-O1 工具栏元素与空状态', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '合并记忆' }).click()
      await expect(page.locator('.organize-select')).toBeVisible()
      await expect(page.locator('.organize-select')).toHaveValue('0.85')
      await expect(page.locator('.btn-accent', { hasText: '开始分析' })).toBeVisible()
      await expect(page.locator('.empty-text')).toContainText('点击「开始分析」查找重复记忆')
    })
  })

  test.describe('记忆数据 Tab', () => {
    test('MEM-C1 图表渲染与统计', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '记忆数据' }).click()
      await expect(page.locator('.chart-section')).toBeVisible()
      await expect(page.locator('.chart-title')).toHaveText('记忆数据')
      // 数据视图 Tab：累计曲线默认激活
      await expect(page.locator('.data-tab.active')).toHaveText('累计曲线')
      // 时间范围 Tab
      await expect(page.locator('.chart-tab')).toHaveCount(4)
      await expect(page.locator('.chart-tab.active')).toHaveText('近24小时')
      // ECharts canvas
      await expect(page.locator('.chart-canvas canvas').first()).toBeVisible({ timeout: 15000 })
      // 统计数值
      await expect(page.locator('.stat-box .sb-label', { hasText: '记忆总数' })).toBeVisible()
    })

    test('OV-07/08 数据视图与时间范围切换', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '记忆数据' }).click()
      // 切新增曲线并切回
      await page.locator('.data-tab', { hasText: '新增曲线' }).click()
      await expect(page.locator('.data-tab.active')).toHaveText('新增曲线')
      await page.locator('.data-tab', { hasText: '累计曲线' }).click()
      await expect(page.locator('.data-tab.active')).toHaveText('累计曲线')
      // 默认（近24小时）显示 2 个统计框：记忆总数 / 24h新增
      await expect(page.locator('.stat-box')).toHaveCount(2)
      await expect(page.locator('.sb-label', { hasText: '记忆总数' })).toBeVisible()
      await expect(page.locator('.sb-label', { hasText: '24h新增' })).toBeVisible()
      // 切"全部"时增量统计隐藏（只剩 记忆总数）
      await page.locator('.chart-tab', { hasText: '全部' }).click()
      await expect(page.locator('.stat-box')).toHaveCount(1)
      // 切回恢复 2 个
      await page.locator('.chart-tab', { hasText: '近24小时' }).click()
      await expect(page.locator('.stat-box')).toHaveCount(2)
    })
  })

  test.describe('图谱 Tab', () => {
    test('MEM-G1 工具栏与统计渲染', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '图谱' }).click()
      await expect(page.locator('.graph-panel')).toBeVisible()
      await expect(page.locator('.graph-toolbar')).toBeVisible()
      await expect(page.locator('.graph-info')).toBeVisible()
      await expect(page.locator('.btn-refresh')).toBeVisible()
    })
  })

  test.describe('实体 Tab', () => {
    test('MEM-E1 统计卡片渲染且数值非负', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '实体' }).click()
      await expect(page.locator('.entity-stats-row')).toBeVisible()
      await expect(page.locator('.entity-stat-card')).toHaveCount(4)
      const labels = ['实体节点', '实体提及', '记忆关联', '内存图 (节点/边)']
      for (const l of labels) {
        await expect(page.locator('.esc-label', { hasText: l })).toBeVisible()
      }
      const values = await page.locator('.esc-value').allTextContents()
      for (const v of values) {
        const n = parseInt(v, 10)
        if (!Number.isNaN(n)) expect(n).toBeGreaterThanOrEqual(0)
      }
      await expect(page.locator('.erc-title')).toHaveText('重建实体网络')
    })
  })

  test.describe('设置 Tab', () => {
    test('MEM-SET1 显示记忆设置固定启用提示', async ({ page }) => {
      await gotoMemory(page)
      await page.locator('.nav-tab', { hasText: '⚙ 设置' }).click()
      await expect(page.locator('.empty-text')).toContainText('记忆功能全部固定启用')
    })
  })
})
