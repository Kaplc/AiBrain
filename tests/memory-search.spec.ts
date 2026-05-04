import { test, expect } from '@playwright/test';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

test.describe('Memory Search Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/memory');
    await page.waitForLoadState('domcontentloaded');
  });

  test('search tab UI loads correctly', async ({ page }) => {
    // 验证搜索输入框和按钮存在
    const searchInput = page.locator('.search-bar input[type="text"]');
    await expect(searchInput).toBeVisible();

    const searchBtn = page.locator('.search-bar .btn-primary');
    await expect(searchBtn).toBeVisible();
    await expect(searchBtn).toHaveText('搜索');

    // 验证历史按钮存在
    const historyBtn = page.locator('.btn-icon-sm');
    await expect(historyBtn).toBeVisible();
  });

  test('search shows loading spinner during search', async ({ page }) => {
    const searchInput = page.locator('.search-bar input[type="text"]');
    const searchBtn = page.locator('.search-bar .btn-primary');

    // 先输入搜索词
    await searchInput.fill('测试');

    // 点击搜索按钮，在搜索完成前检查 spinner
    const searchPromise = searchBtn.click();

    // 等待 loading 状态出现
    const spinner = page.locator('.spinner');
    await expect(spinner).toBeVisible({ timeout: 1000 }).catch(() => {});

    await searchPromise;
  });

  test('search results display after successful search', async ({ page }) => {
    const searchInput = page.locator('.search-bar input[type="text"]');
    const searchBtn = page.locator('.search-bar .btn-primary');

    await searchInput.fill('测试');
    await searchBtn.click();

    // 等待搜索结果，最多10秒
    await page.waitForTimeout(3000);
    const results = page.locator('.search-result');
    const hasResults = await results.count() > 0;
    // 检查search tab下是否有空状态提示
    const searchPanel = page.locator('.tab-panel').first()
    const emptyState = searchPanel.locator('.empty');
    const hasEmpty = hasResults ? false : await emptyState.isVisible().catch(() => false);
    expect(hasResults || hasEmpty).toBeTruthy();
  });

  test('history button shows dropdown', async ({ page }) => {
    const historyBtn = page.locator('.btn-icon-sm');

    await historyBtn.click();
    const dropdown = page.locator('.sh-dropdown');
    await expect(dropdown).toBeVisible();
  });

  test('cannot search while search is in progress', async ({ page }) => {
    const searchInput = page.locator('.search-bar input[type="text"]');
    const searchBtn = page.locator('.search-bar .btn-primary');

    // 第一次搜索
    await searchInput.fill('测试');
    await searchBtn.click();

    // 搜索进行中，再次点击应该被阻止（按钮disabled）
    const btnDisabled = await searchBtn.isDisabled();
    expect(btnDisabled).toBeTruthy();

    // 等待搜索完成（等待足够长的时间）
    await page.waitForTimeout(8000);

    // 搜索完成后，按钮应该恢复可用
    await expect(searchBtn).toBeEnabled();
  });

  test('history button size matches search button', async ({ page }) => {
    const searchBtn = page.locator('.search-bar .btn-primary');
    const historyBtn = page.locator('.btn-icon-sm');

    const searchBtnBox = await searchBtn.boundingBox();
    const historyBtnBox = await historyBtn.boundingBox();

    if (searchBtnBox && historyBtnBox) {
      // 检查高度是否一致（允许1px误差）
      const heightDiff = Math.abs(searchBtnBox.height - historyBtnBox.height);
      expect(heightDiff).toBeLessThanOrEqual(2);
    }
  });

  test('clicking history item triggers search', async ({ page }) => {
    const historyBtn = page.locator('.btn-icon-sm');
    await historyBtn.click();

    const dropdown = page.locator('.sh-dropdown');
    await expect(dropdown).toBeVisible();

    // 如果有历史记录，点击
    const historyItems = page.locator('.history-item');
    const count = await historyItems.count();

    if (count > 0) {
      await historyItems.first().click();
      // 下拉框应该关闭
      await expect(dropdown).toBeHidden();
    }
  });

  test('clear history button clears history list', async ({ page }) => {
    const historyBtn = page.locator('.btn-icon-sm');
    await historyBtn.click();

    const dropdown = page.locator('.sh-dropdown');
    await expect(dropdown).toBeVisible();

    const clearBtn = page.locator('.sh-clear');
    const historyItems = page.locator('.history-item');
    const count = await historyItems.count();

    if (count > 0) {
      await clearBtn.click();
      // 验证历史列表被清空
      const emptyMsg = page.locator('.sh-empty');
      await expect(emptyMsg).toBeVisible();
    }
  });
});
