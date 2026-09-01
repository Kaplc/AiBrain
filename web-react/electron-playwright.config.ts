import { defineConfig } from '@playwright/test'

/* Electron E2E 配置：_electron 启动器加载 electron/main.js
 * 运行：npx playwright test -c electron-playwright.config.ts
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: ['electron.spec.ts', 'electron-dev.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 120000,
  use: {
    trace: 'off',
    screenshot: 'only-on-failure',
  },
})
