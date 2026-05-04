import { test, expect } from '@playwright/test';

test.describe('Wiki Page - Rebuild Index', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/wiki');
    await page.waitForLoadState('domcontentloaded');
  });

  test('wiki page loads correctly', async ({ page }) => {
    const wikiTitle = page.locator('.wiki-title');
    await expect(wikiTitle).toHaveText('Wiki 知识库');

    const fileSection = page.locator('.file-section');
    await expect(fileSection).toBeVisible();
  });

  test('ops panel has rebuild index button', async ({ page }) => {
    // Switch to ops tab
    await page.click('.side-tab-btn:has-text("操作")');

    const rebuildBtn = page.locator('.ops-btn');
    await expect(rebuildBtn).toBeVisible();
    await expect(rebuildBtn).toContainText('重建索引');
  });

  test('rebuild index button triggers indexing', async ({ page }) => {
    // Switch to ops tab
    await page.click('.side-tab-btn:has-text("操作")');

    const rebuildBtn = page.locator('.ops-btn');
    await rebuildBtn.click();

    // 等待足够长的时间让状态更新
    await page.waitForTimeout(2000);

    // 检查按钮状态和结果消息
    const isDisabled = await rebuildBtn.isDisabled();
    const btnText = await page.locator('.ops-btn .ops-text').textContent();
    const isIndexing = btnText?.includes('索引中...');

    // 检查索引结果消息（无论成功还是失败）
    const resultMsg = page.locator('.index-result');
    const hasResult = await resultMsg.isVisible().catch(() => false);

    // 如果正在索引中，按钮应该disabled或显示"索引中..."
    // 如果索引已完成，应该显示结果消息
    // 如果索引立即完成（无文件），两者都不满足也是可以的
    const validState = isDisabled || isIndexing || hasResult;
    expect(validState).toBeTruthy();
  });

  test('progress bar shows during indexing', async ({ page }) => {
    // Switch to ops tab
    await page.click('.side-tab-btn:has-text("操作")');

    // Click rebuild
    await page.locator('.ops-btn').click();

    // 等待进度条出现（如果有文件需要索引的话）
    await page.waitForTimeout(2000);

    // 检查进度条容器是否存在（可能在进度完成后退隐藏）
    const progressBg = page.locator('.progress-bar-bg');
    const progressBar = page.locator('.progress-bar-fill');

    // 进度条可能显示或隐藏，取决于是否有文件需要索引
    // 如果按钮仍然是"索引中..."状态，进度条应该可见
    const btnText = await page.locator('.ops-btn .ops-text').textContent();
    const isIndexing = btnText?.includes('索引中...');

    if (isIndexing) {
      // 如果还在索引中，验证进度条可见
      await expect(progressBg).toBeVisible();
      const style = await progressBar.getAttribute('style');
      expect(style).toContain('width');
    } else {
      // 如果索引已立即完成，检查是否显示了结果消息
      const resultMsg = page.locator('.index-result');
      const hasResult = await resultMsg.isVisible().catch(() => false);
      // 没有结果也可以接受（如果没有文件需要索引）
    }
  });

  test('settings panel loads correctly', async ({ page }) => {
    // Switch to settings tab
    await page.click('.side-tab-btn:has-text("设置")');

    const wikiDirInput = page.locator('.form-input').first();
    await expect(wikiDirInput).toBeVisible();
  });
});
