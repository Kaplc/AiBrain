import { defineConfig, devices } from '@playwright/test';
import { readFileSync } from 'fs';

const portFile = '.port_config';
let basePort = '19398';
try {
  const ports = readFileSync(portFile, 'utf-8').trim().split(',');
  basePort = ports[0] || '19398';
} catch { /* use default */ }

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: process.env.BASE_URL || `http://127.0.0.1:${basePort}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
