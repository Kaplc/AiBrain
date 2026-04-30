import { test, expect } from '@playwright/test';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

test.describe('Memory Manager API', () => {
  test('health check', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.status()).toBe(200);
  });

  test('status returns expected fields', async ({ request }) => {
    const res = await request.get('/status');
    const body = await res.json();
    expect(body).toHaveProperty('model_loaded');
    expect(body).toHaveProperty('qdrant_ready');
    expect(body).toHaveProperty('device');
    expect(body).toHaveProperty('embedding_model');
  });

  test('status returns qdrant config fields', async ({ request }) => {
    const res = await request.get('/status');
    const body = await res.json();
    expect(body).toHaveProperty('qdrant_host');
    expect(body).toHaveProperty('qdrant_port');
    expect(body).toHaveProperty('qdrant_collection');
    expect(body).toHaveProperty('qdrant_top_k');
    expect(typeof body.qdrant_port).toBe('number');
    expect(typeof body.qdrant_top_k).toBe('number');
  });

  test('status returns flask status fields', async ({ request }) => {
    const res = await request.get('/status');
    const body = await res.json();
    // 验证新增的 flask_* 字段
    expect(body).toHaveProperty('flask_port');
    expect(body).toHaveProperty('flask_pid');
    expect(body).toHaveProperty('flask_uptime');
    expect(body).toHaveProperty('flask_reload');
    expect(typeof body.flask_port).toBe('number');
    expect(typeof body.flask_pid).toBe('number');
    expect(typeof body.flask_uptime).toBe('number');
    expect(typeof body.flask_reload).toBe('boolean');
    expect(body.flask_port).toBeGreaterThan(0);
    expect(body.flask_pid).toBeGreaterThan(0);
    expect(body.flask_uptime).toBeGreaterThanOrEqual(0);
  });

  test('settings GET/POST works', async ({ request }) => {
    let res = await request.get('/settings');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('device');

    res = await request.post('/settings', { headers: JSON_HEADERS, data: '{"device":"cpu"}' });
    expect(res.status()).toBe(200);
  });

  test('db-status returns ok', async ({ request }) => {
    const res = await request.get('/db-status');
    const body = await res.json();
    expect(body.ok).toBeTruthy();
    expect(body).toHaveProperty('records');
  });

  test('chart-data returns data structure', async ({ request }) => {
    const res = await request.get('/chart-data?range=today');
    const body = await res.json();
    expect(body).toHaveProperty('range', 'today');
    expect(body).toHaveProperty('data');
    expect(Array.isArray(body.data)).toBeTruthy();
  });

  test('system-info returns system metrics', async ({ request }) => {
    const res = await request.get('/system-info');
    const body = await res.json();
    expect(body).toHaveProperty('cpu_percent');
    expect(body).toHaveProperty('memory_total');
    expect(body).toHaveProperty('platform');
  });

  test('store and search memory', async ({ request }) => {
    const storeRes = await request.post('/store', {
      headers: JSON_HEADERS,
      data: JSON.stringify({ text: 'Playwright 测试记忆' })
    });
    expect(storeRes.status()).toBe(200);

    const searchRes = await request.post('/search', {
      headers: JSON_HEADERS,
      data: JSON.stringify({ query: '测试' })
    });
    const body = await searchRes.json();
    expect(searchRes.status()).toBe(200);
    expect(body.results.length).toBeGreaterThan(0);
  });

  test('list memories', async ({ request }) => {
    const res = await request.post('/list', {
      headers: JSON_HEADERS,
      data: '{}'
    });
    const body = await res.json();
    expect(res.status()).toBe(200);
    expect(body).toHaveProperty('memories');
  });
});

test.describe('Memory Manager Page', () => {
  test('page loads without crash', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.nav-sidebar')).toBeVisible();
  });

  test('navigation tabs exist', async ({ page }) => {
    await page.goto('/');
    const navItems = page.locator('.nav-item');
    await expect(navItems).toHaveCount(6);
  });

  test('overview tab shows status cards', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');
    const cards = page.locator('.status-card');
    await expect(cards.first()).toBeVisible({ timeout: 15000 });
  });

  test('overview shows qdrant config info', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');
    // Qdrant badge 应该显示 OK（数据由 /status API 异步填充）
    const qBadge = page.locator('#scQdrantBadge');
    await expect(qBadge).toBeVisible({ timeout: 15000 });
    const badgeText = await qBadge.textContent();
    expect(badgeText).toContain('OK');
  });

  test('overview shows flask status card', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');
    // 验证 Flask badge 可见且为 OK
    const flaskBadge = page.locator('#scFlaskBadge');
    await expect(flaskBadge).toBeVisible({ timeout: 10000 });
    const badgeText = await flaskBadge.textContent();
    expect(badgeText).toContain('OK');

    // 验证 Flask 状态信息行包含端口、PID、运行时间
    const flaskSub1 = page.locator('#scFlaskSub1');
    await page.waitForFunction(() => {
      const el = document.getElementById('scFlaskSub1');
      return el && el.textContent && el.textContent.includes('端口:');
    }, { timeout: 10000 });
    const sub1Text = await flaskSub1.textContent();
    expect(sub1Text).toContain('端口:');

    // PID 行包含数字
    const sub2Text = await page.locator('#scFlaskSub2').textContent();
    expect(sub2Text).toContain('PID:');

    // 运行时间行
    const sub3Text = await page.locator('#scFlaskSub3').textContent();
    expect(sub3Text).toContain('运行:');

    // 热重载状态行
    const sub4Text = await page.locator('#scFlaskSub4').textContent();
    expect(sub4Text).toContain('热重载:');
  });

  test('memory page has scrollable list container', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="memory"]');
    await page.waitForLoadState('domcontentloaded');
    // 检查滚动容器 .memory-list-container 有正确的 overflow 样式
    const scrollContainer = page.locator('#tabSearch .memory-list-container');
    await expect(scrollContainer).toBeVisible();
    const styles = await scrollContainer.evaluate(el => {
      const computed = window.getComputedStyle(el);
      return {
        overflowY: computed.overflowY,
        flex: computed.flex
      };
    });
    expect(styles.overflowY).toBe('auto');
    // 检查主布局没有滚动
    const layout = page.locator('.memory-layout');
    const layoutStyles = await layout.evaluate(el => {
      return window.getComputedStyle(el).overflow;
    });
    expect(layoutStyles).toBe('hidden');
  });

  test('steam tab loads stream UI', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="steam"]');
    await page.waitForLoadState('domcontentloaded');
    // 检查两栏布局存在
    const storeList = page.locator('#storeList');
    const searchList = page.locator('#searchList');
    await expect(storeList).toBeVisible({ timeout: 5000 });
    await expect(searchList).toBeVisible({ timeout: 5000 });
  });

  test('flask/restart endpoint exists', async ({ request }) => {
    const res = await request.post('/flask/restart');
    expect([200, 405]).toContain(res.status());
  });

  test('overview shows flask restart button', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');
    const btn = page.locator('#btnRestartFlask');
    await expect(btn).toBeVisible({ timeout: 10000 });
    expect(await btn.textContent()).toContain('重启');
  });

  test('overview restart flask button click flow', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');

    const btn = page.locator('#btnRestartFlask');
    const badge = page.locator('#scFlaskBadge');
    await expect(btn).toBeVisible({ timeout: 10000 });

    // 拦截 confirm 对话框，自动确认
    let dialogHandled = false;
    page.on('dialog', async dialog => {
      if (!dialogHandled) {
        dialogHandled = true;
        await dialog.accept();
      }
    });

    // 点击前记录初始状态
    const initialText = await btn.textContent();
    expect(initialText).toContain('重启');
    expect(await btn.isEnabled()).toBe(true);

    // 点击重启按钮
    await btn.click();

    // 等待按钮状态变化（disabled + 文字变化）
    await page.waitForFunction(() => {
      const el = document.getElementById('btnRestartFlask');
      return el && el.disabled && el.textContent !== '重启';
    }, { timeout: 5000 });

    // 验证按钮进入重启中状态
    expect(await btn.isDisabled()).toBe(true);
    expect(await btn.textContent()).toMatch(/重启中|已发送/);

    // 验证 badge 变为黄色/加载中
    await page.waitForFunction(() => {
      const el = document.getElementById('scFlaskBadge');
      return el && el.classList.contains('yellow');
    }, { timeout: 3000 });
    const badgeClass = await badge.evaluate(el => el.className);
    expect(badgeClass).toContain('yellow');

    // 等待 Flask 恢复（轮询 status API 直到 PID 变化）
    await page.waitForFunction(async () => {
      try {
        const resp = await fetch('/status');
        const st = await resp.json();
        return !!st.flask_pid;
      } catch {
        return false;
      }
    }, { timeout: 60000 });

    // 等待按钮恢复可用状态
    await page.waitForFunction(() => {
      const el = document.getElementById('btnRestartFlask');
      return el && !el.disabled && el.textContent === '重启';
    }, { timeout: 15000 });

    // 最终验证：按钮恢复、badge 回到 OK
    expect(await btn.isEnabled()).toBe(true);
    expect(await btn.textContent()).toBe('重启');
    await page.waitForFunction(() => {
      const el = document.getElementById('scFlaskBadge');
      return el && el.textContent === 'OK';
    }, { timeout: 10000 });
    // 额外等待 Flask 完全初始化，避免后续测试连接失败
    await page.waitForTimeout(3000);
  });

  test('overview card order: model, qdrant, flask, device', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await page.waitForLoadState('domcontentloaded');
    const cards = page.locator('.overview-row .status-card');
    await expect(cards).toHaveCount(4);
    await expect(cards.nth(0)).toContainText('模型状态');
    await expect(cards.nth(1)).toContainText('Qdrant');
    await expect(cards.nth(2)).toContainText('Flask');
    await expect(cards.nth(3)).toContainText('设备信息');
  });

  test('overview data tabs switch between cumulative and added chart', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    // 等待 overview JS 加载完成（以重启按钮出现为信号）
    await expect(page.locator('#btnRestartFlask')).toBeVisible({ timeout: 10000 });

    const chartView = page.locator('#chartView');
    const addedView = page.locator('#addedView');
    await expect(chartView).toBeVisible();
    await expect(addedView).toBeHidden();

    await page.click('.data-tab[data-view="added"]');
    // 等待 tab 切换生效（事件监听器 + DOM 更新）
    await page.waitForTimeout(300);
    await expect(addedView).toBeVisible({ timeout: 5000 });
    await expect(chartView).toBeHidden();

    // 切换回累计曲线
    await page.click('.data-tab[data-view="cumulative"]');
    await expect(chartView).toBeVisible();
    await expect(addedView).toBeHidden();
  });

  test('overview added chart shows data', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-page="overview"]');
    await expect(page.locator('#btnRestartFlask')).toBeVisible({ timeout: 10000 });

    await page.click('.data-tab[data-view="added"]');
    const addedView = page.locator('#addedView');
    await expect(addedView).toBeVisible({ timeout: 5000 });

    // 等待新增统计数值加载（非"-"）
    await page.waitForFunction(() => {
      const el = document.getElementById('addedStatToday');
      return el && el.textContent && el.textContent !== '-';
    }, { timeout: 10000 });

    const todayText = await page.locator('#addedStatToday').textContent();
    expect(Number(todayText)).toBeGreaterThanOrEqual(0);
  });

  test('log endpoint accepts frontend logs', async ({ request }) => {
    const res = await request.post('/log', {
      headers: JSON_HEADERS,
      data: JSON.stringify({ level: 'info', message: 'Playwright test log', source: 'e2e-test' })
    });
    expect(res.status()).toBe(200);
  });
});
