import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = resolve(fileURLToPath(import.meta.url), '..', '..')

const portConfigPath = resolve(__dirname, '.port_config')
let apiPort = '8577'
try {
  const content = readFileSync(portConfigPath, 'utf-8').trim()
  const ports = content.split(',').map((p: string) => parseInt(p, 10))
  if (ports.length >= 1 && !isNaN(ports[0])) {
    apiPort = String(ports[0])
  }
} catch {}

console.log('[vite] apiPort =', apiPort, 'from', portConfigPath)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'web', 'src'),
    },
  },
  server: {
    port: 3000,
    host: '127.0.0.1',
    proxy: {
      // SPA 页面路由
      '/status': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/stream': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // 状态栏 API
      '/statusbar/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Overview API
      '/overview/model': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/qdrant': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/flask': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/system-info': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/db-status': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/model-info': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview/flask/restart': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Settings API
      '/settings/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings/aibrain-config': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings/reload-model': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings/save-aibrain-config': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings/check-path': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings/select-directory': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Memory API
      '/memory/store': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/search': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/list': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/delete': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/count': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/organize/dedup': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/organize/refine': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/organize/apply': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory/search-history': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Stream API
      '/stream/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Logs API
      '/logs/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Chart API
      '/chart-data': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Wiki API
      '/wiki/search': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/list': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/index': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/index-progress': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/index-log': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/log': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki/settings': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      // Frontend log
      '/log': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    esbuild: {
      drop: [],
    },
  },
})