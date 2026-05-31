import { test, expect } from '@playwright/test'

/*
 * Memory Search E2E Test
 *
 * Tests the search functionality on the Memory page (/memory).
 * Covers: search bar UI, search execution, result rendering,
 * empty state, search history, keyboard interaction, loading state,
 * and delete from results.
 *
 * Key CSS selectors from SearchPanel.vue:
 *   .search-bar input          - search input field
 *   .search-bar .btn-primary   - search button
 *   .btn-icon-sm               - history toggle button
 *   .sh-dropdown               - history dropdown panel
 *   .sh-clear                  - clear history button
 *   .history-item              - individual history entry
 *   .search-loading            - loading indicator
 *   .memory-list               - results container
 *   .memory-card.search-result - individual result card
 *   .memory-text               - result text content
 *   .memory-meta               - result metadata row
 *   .memory-time               - timestamp
 *   .memory-score              - similarity score
 *   .memory-id                 - short ID
 *   .del-btn                   - delete button on result card
 *   .empty                     - empty state container
 *   .empty-icon / .empty-text  - empty state elements
 */

test.describe('Memory - Search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    // Ensure search tab is active (it is the default tab)
    const searchTab = page.locator('.nav-tab:has-text("搜索记忆")')
    await searchTab.click()
    await expect(searchTab).toHaveClass(/active/)
  })

  // ── Search bar UI ─────────────────────────────────────

  test('search input is visible and has correct placeholder', async ({ page }) => {
    const input = page.locator('.search-bar input')
    await expect(input).toBeVisible()
    await expect(input).toHaveAttribute('placeholder', '搜索相关记忆...')
  })

  test('search button is visible and labeled', async ({ page }) => {
    const btn = page.locator('.search-bar .btn-primary')
    await expect(btn).toBeVisible()
    await expect(btn).toHaveText('搜索')
  })

  test('search history toggle button is visible', async ({ page }) => {
    const historyBtn = page.locator('.search-history-wrap .btn-icon-sm')
    await expect(historyBtn).toBeVisible()
  })

  // ── Initial empty state ───────────────────────────────

  test('shows initial prompt before any search', async ({ page }) => {
    // Before searching, should show the "search to see results" prompt
    const emptyText = page.locator('.tab-panel:has(.search-bar) .empty-text')
    await expect(emptyText).toHaveText('搜索记忆以查看结果')
  })

  // ── Search execution ──────────────────────────────────

  test('clicking search button with input triggers search', async ({ page }) => {
    const input = page.locator('.search-bar input')
    const searchBtn = page.locator('.search-bar .btn-primary')

    // Set up API response interceptor
    const searchPromise = page.waitForResponse(
      (resp) => resp.url().includes('/memory/search') && resp.status() === 200
    )

    await input.fill('测试')
    await searchBtn.click()
    const response = await searchPromise

    expect(response.status()).toBe(200)
    // After search completes, activeQuery should be set, so results area updates
    const memoryList = page.locator('.tab-panel:has(.search-bar) .memory-list')
    await expect(memoryList).toBeVisible()
  })

  test('pressing Enter in input triggers search', async ({ page }) => {
    const input = page.locator('.search-bar input')

    const searchPromise = page.waitForResponse(
      (resp) => resp.url().includes('/memory/search') && resp.status() === 200
    )

    await input.fill('Enter键搜索')
    await input.press('Enter')
    const response = await searchPromise

    expect(response.status()).toBe(200)
  })

  test('empty input does not trigger search', async ({ page }) => {
    const input = page.locator('.search-bar input')
    // Fill then clear to ensure it's empty
    await input.fill('')
    await input.press('Enter')

    // Should still show the initial prompt, no loading state
    const emptyText = page.locator('.tab-panel:has(.search-bar) .empty-text')
    await expect(emptyText).toHaveText('搜索记忆以查看结果')
  })

  test('whitespace-only input does not trigger search', async ({ page }) => {
    const input = page.locator('.search-bar input')
    await input.fill('   ')
    await input.press('Enter')

    // Should still show the initial prompt
    const emptyText = page.locator('.tab-panel:has(.search-bar) .empty-text')
    await expect(emptyText).toHaveText('搜索记忆以查看结果')
  })

  // ── Loading state ─────────────────────────────────────

  test('shows loading indicator during search', async ({ page }) => {
    // Delay the API response to catch the loading state
    await page.route('**/memory/search', async (route) => {
      await new Promise((r) => setTimeout(r, 1000))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    })

    const input = page.locator('.search-bar input')
    const searchBtn = page.locator('.search-bar .btn-primary')

    await input.fill('加载测试')
    await searchBtn.click()

    // Loading indicator should appear
    const loading = page.locator('.tab-panel:has(.search-bar) .search-loading')
    await expect(loading).toBeVisible()
    await expect(loading).toContainText('搜索中...')

    // Wait for the delayed response to complete
    await expect(loading).toBeHidden({ timeout: 5000 })
  })

  test('search input and button are disabled during loading', async ({ page }) => {
    await page.route('**/memory/search', async (route) => {
      await new Promise((r) => setTimeout(r, 1000))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    })

    const input = page.locator('.search-bar input')
    const searchBtn = page.locator('.search-bar .btn-primary')

    await input.fill('禁用测试')
    await searchBtn.click()

    // Both input and button should be disabled while loading
    await expect(input).toBeDisabled()
    await expect(searchBtn).toBeDisabled()

    // Wait for response
    await page.waitForResponse((resp) => resp.url().includes('/memory/search'))
  })

  // ── Search results rendering ──────────────────────────

  test('search results display memory cards with correct structure', async ({ page }) => {
    // Mock search response with one result
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              id: 'abc123456789def0',
              text: '这是一条测试记忆内容，用于验证搜索结果渲染',
              timestamp: '2026-05-30T10:00:00Z',
              score: 0.92,
              category: 'fact',
            },
          ],
        }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('测试记忆')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Verify result card structure
    const card = page.locator('.memory-card.search-result')
    await expect(card).toHaveCount(1)

    // Text content
    const text = page.locator('.memory-card .memory-text')
    await expect(text).toHaveText('这是一条测试记忆内容，用于验证搜索结果渲染')

    // Meta info: time, score, short ID
    const meta = page.locator('.memory-card .memory-meta')
    await expect(meta).toBeVisible()

    const score = page.locator('.memory-card .memory-score')
    await expect(score).toHaveText('相似度 92.0%')

    const shortId = page.locator('.memory-card .memory-id')
    await expect(shortId).toHaveText('abc12345...')

    // Delete button exists
    const delBtn = page.locator('.memory-card .del-btn')
    await expect(delBtn).toBeVisible()
  })

  test('multiple results render as separate cards', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            { id: '1111111111111111', text: '第一条结果', timestamp: '2026-05-30T10:00:00Z', score: 0.95 },
            { id: '2222222222222222', text: '第二条结果', timestamp: '2026-05-29T08:00:00Z', score: 0.80 },
            { id: '3333333333333333', text: '第三条结果', timestamp: '2026-05-28T06:00:00Z', score: 0.65 },
          ],
        }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('多条')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    const cards = page.locator('.memory-card.search-result')
    await expect(cards).toHaveCount(3)

    // Verify each card has distinct text
    await expect(cards.nth(0).locator('.memory-text')).toHaveText('第一条结果')
    await expect(cards.nth(1).locator('.memory-text')).toHaveText('第二条结果')
    await expect(cards.nth(2).locator('.memory-text')).toHaveText('第三条结果')
  })

  test('score is not shown when not provided by API', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            { id: 'noscore000000000', text: '无分数结果', timestamp: '2026-05-30T10:00:00Z' },
          ],
        }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('无分数')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Card should exist but no score element
    const card = page.locator('.memory-card.search-result')
    await expect(card).toHaveCount(1)
    const score = page.locator('.memory-card .memory-score')
    await expect(score).toHaveCount(0)
  })

  // ── Empty results ─────────────────────────────────────

  test('shows empty result message when search returns nothing', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('完全不存在的关键词xyz')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Should show "没有找到相关记忆"
    const emptyText = page.locator('.tab-panel:has(.search-bar) .empty-text')
    await expect(emptyText).toHaveText('没有找到相关记忆')
  })

  // ── Search history ────────────────────────────────────

  test('search history dropdown opens on toggle click', async ({ page }) => {
    // Perform a search to populate history
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    )
    // Also mock the history endpoint
    await page.route('**/memory/search-history', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ history: [{ query: '历史搜索词' }] }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('历史测试')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Click history toggle button
    const historyBtn = page.locator('.search-history-wrap .btn-icon-sm')
    await historyBtn.click()

    // Dropdown should be visible
    const dropdown = page.locator('.sh-dropdown')
    await expect(dropdown).toBeVisible()

    // Should contain the search history header
    const header = page.locator('.sh-dropdown-header span')
    await expect(header).toHaveText('搜索历史')
  })

  test('clear history button empties the list', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    )
    await page.route('**/memory/search-history', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ history: [{ query: '旧搜索词' }] }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('清除历史测试')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Open history
    await page.locator('.search-history-wrap .btn-icon-sm').click()
    await expect(page.locator('.sh-dropdown')).toBeVisible()

    // Mock DELETE for clearing history
    await page.route('**/memory/search-history', (route) => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      }
      return route.fallback()
    })

    // Click clear
    await page.locator('.sh-clear').click()

    // Should show empty state in dropdown
    await expect(page.locator('.sh-empty')).toHaveText('暂无搜索历史')
  })

  test('clicking a history item fills input and searches', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    )
    await page.route('**/memory/search-history', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ history: [{ query: '历史关键词' }] }),
      })
    )

    // First search to populate history
    const input = page.locator('.search-bar input')
    await input.fill('任意搜索')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Open history and click the history item
    await page.locator('.search-history-wrap .btn-icon-sm').click()
    await expect(page.locator('.history-item')).toBeVisible()

    const searchPromise = page.waitForResponse((r) => r.url().includes('/memory/search'))
    await page.locator('.history-item').click()
    await searchPromise

    // Input should be filled with the history keyword
    await expect(input).toHaveValue('历史关键词')
  })

  test('history dropdown closes on outside click', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      })
    )
    await page.route('**/memory/search-history', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ history: [{ query: '某词' }] }),
      })
    )

    // Perform a search to load history
    const input = page.locator('.search-bar input')
    await input.fill('测试')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Open history
    await page.locator('.search-history-wrap .btn-icon-sm').click()
    await expect(page.locator('.sh-dropdown')).toBeVisible()

    // Click outside (on the nav area)
    await page.locator('.memory-nav').click()

    // Dropdown should close
    await expect(page.locator('.sh-dropdown')).not.toBeVisible()
  })

  // ── Delete from search results ────────────────────────

  test('delete button removes a result card', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            { id: 'del-test-00000000', text: '要删除的记忆', timestamp: '2026-05-30T10:00:00Z', score: 0.9 },
          ],
        }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('删除')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Verify card exists
    const card = page.locator('.memory-card.search-result')
    await expect(card).toHaveCount(1)

    // Mock delete API
    await page.route('**/memory/delete', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ result: '删除成功' }),
      })
    )

    // Click delete
    await page.locator('.memory-card .del-btn').click()
    await page.waitForResponse((r) => r.url().includes('/memory/delete'))

    // Card should be removed (slide-out animation then remove)
    await expect(page.locator('.memory-card.search-result')).toHaveCount(0, { timeout: 2000 })
  })

  // ── Error handling ────────────────────────────────────

  test('shows error toast when search API fails', async ({ page }) => {
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: '服务器错误' }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('错误测试')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Should show error toast
    const toast = page.locator('.toast-item')
    await expect(toast).toBeVisible({ timeout: 3000 })
  })

  // ── Sequential searches ───────────────────────────────

  test('performing a new search replaces previous results', async ({ page }) => {
    // First search
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            { id: 'first-00000000000', text: '第一次搜索结果', timestamp: '2026-05-30T10:00:00Z', score: 0.9 },
          ],
        }),
      })
    )

    const input = page.locator('.search-bar input')
    await input.fill('第一次')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    await expect(page.locator('.memory-card.search-result')).toHaveCount(1)
    await expect(page.locator('.memory-card .memory-text')).toHaveText('第一次搜索结果')

    // Second search with different mock
    await page.route('**/memory/search', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            { id: 'second-000000000', text: '第二次搜索结果A', timestamp: '2026-05-30T12:00:00Z', score: 0.88 },
            { id: 'second-000000001', text: '第二次搜索结果B', timestamp: '2026-05-30T12:01:00Z', score: 0.75 },
          ],
        }),
      })
    )

    await input.fill('第二次')
    await page.locator('.search-bar .btn-primary').click()
    await page.waitForResponse((r) => r.url().includes('/memory/search'))

    // Should now show 2 new results, old one gone
    await expect(page.locator('.memory-card.search-result')).toHaveCount(2)
    await expect(page.locator('.memory-card').nth(0).locator('.memory-text')).toHaveText('第二次搜索结果A')
    await expect(page.locator('.memory-card').nth(1).locator('.memory-text')).toHaveText('第二次搜索结果B')
  })
})
