import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = resolve(fileURLToPath(import.meta.url), '..', '..')

const portConfigPath = resolve(__dirname, '.port_config')
let port = 19398
try {
  const content = readFileSync(portConfigPath, 'utf-8').trim()
  const firstPort = parseInt(content.split(',')[0], 10)
  if (!isNaN(firstPort)) port = firstPort
} catch {}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:5174`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  launchOptions: {
    args: ['--proxy-bypass-list=127.0.0.1;localhost', '--proxy-server=direct://'],
  },
  webServer: {
    command: 'npx serve dist -l 5174',
    port: 5174,
    reuseExistingServer: true,
    timeout: 30000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})