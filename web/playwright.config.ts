import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = resolve(fileURLToPath(import.meta.url), '..', '..')

// 动态读取端口配置
const portConfigPath = resolve(__dirname, '.port_config')
let port = 19398
try {
  const content = readFileSync(portConfigPath, 'utf-8').trim()
  const firstPort = parseInt(content.split(',')[0], 10)
  if (!isNaN(firstPort)) port = firstPort
} catch {
  // 使用默认值
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:5173`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'echo "server check"',
    port: 5173,
    reuseExistingServer: true,
    timeout: 10000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})