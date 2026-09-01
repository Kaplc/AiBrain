/* 流页（TC-STREAM）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

function streamPayload(action: string, id: number, content: string, status = 'done') {
  return {
    items: [{ id, action, content, memory_id: 'mem-' + id, status, created_at: '2026-09-01 10:00:00' }],
  }
}

test.describe('TC-STREAM 流页', () => {
  test('STREAM-01/02 标题计数与三列布局', async ({ page }) => {
    await page.route('**/stream/api?action=store*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(streamPayload('store', 1, '保存内容A')) }))
    await page.route('**/stream/api?action=search*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(streamPayload('search', 2, '查询内容B')) }))
    await page.route('**/stream/api?action=delete*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '流' }).first().click()
    await expect(page).toHaveURL(/\/stream/)
    await expect(page.locator('.stream-title')).toHaveText('记忆流')
    await expect(page.locator('.stream-count')).toHaveText('MCP 1 条 / 搜索 1 条 / 删除 0 条')
    // 三列布局
    await expect(page.locator('.stream-column')).toHaveCount(3)
    const headers = await page.locator('.stream-column-header').allTextContents()
    expect(headers[0]).toContain('保存')
    expect(headers[1]).toContain('查询')
    expect(headers[2]).toContain('删除')
    // 列内容
    await expect(page.locator('.stream-column').nth(0)).toContainText('保存内容A')
    await expect(page.locator('.stream-column').nth(1)).toContainText('查询内容B')
  })

  test('STREAM-03 轮询刷新（2s 周期内数据更新）', async ({ page }) => {
    let n = 0
    await page.route('**/stream/api?action=store*', (route) => {
      n++
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{ id: n, action: 'store', content: '轮询条目' + n, status: 'done', created_at: '2026-09-01 10:00:00' }] }) })
    })
    await page.route('**/stream/api?action=search*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=delete*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '流' }).first().click()
    await expect(page.locator('.stream-column').nth(0)).toContainText('轮询条目1')
    // 等待轮询自动刷新出新条目
    await expect(page.locator('.stream-column').nth(0)).toContainText('轮询条目2', { timeout: 8000 })
  })

  test('STREAM-04 保存操作 → toast + 流刷新', async ({ page }) => {
    await page.route('**/stream/api?action=store*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=search*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=delete*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/memory/store', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: '记忆已保存' }) }))
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '流' }).first().click()
    await page.locator('.stream-action-textarea').fill('E2E流页保存测试')
    await page.locator('.stream-action-btn.store-btn').click()
    await expect(page.locator('.toast.show')).toBeVisible()
  })

  test('STREAM-05 搜索操作 → 结果浮层渲染并可关闭', async ({ page }) => {
    await page.route('**/stream/api?action=store*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=search*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=delete*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ results: [{ id: 'sr-001', text: '浮层搜索结果', timestamp: '2026-09-01 10:00:00' }] }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '流' }).first().click()
    await page.locator('.stream-action-input').first().fill('搜索关键词')
    await page.locator('.stream-action-btn.search-btn').click()
    await expect(page.locator('.search-results-wrap')).toBeVisible()
    await expect(page.locator('.search-results-title')).toContainText('搜索结果 (1)')
    await expect(page.locator('.search-result-text')).toHaveText('浮层搜索结果')
    await page.locator('.search-results-close').click()
    await expect(page.locator('.search-results-wrap')).toHaveCount(0)
  })

  test('STREAM-06 删除操作', async ({ page }) => {
    await page.route('**/stream/api?action=store*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=search*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    await page.route('**/stream/api?action=delete*', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [] }) }))
    let deleteBody: any = null
    await page.route('**/memory/delete', async (route) => {
      deleteBody = route.request().postDataJSON()
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ result: '删除成功' }) })
    })
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '流' }).first().click()
    await page.locator('.stream-action-input').last().fill('mem-delete-target')
    await page.locator('.stream-action-btn.delete-btn').click()
    await expect.poll(() => deleteBody).not.toBeNull()
    expect(deleteBody.memory_id).toBe('mem-delete-target')
    await expect(page.locator('.toast.show')).toBeVisible()
  })
})
