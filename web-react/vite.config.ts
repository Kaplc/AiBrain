import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'

const __dirname = resolve(fileURLToPath(import.meta.url), '..')
const portConfigPath = resolve(__dirname, '..', '.port_config')
let apiPort = '18980'
try {
  const content = readFileSync(portConfigPath, 'utf-8').trim()
  const ports = content.split(',').map((p: string) => parseInt(p, 10))
  if (ports.length >= 1 && !isNaN(ports[0])) apiPort = String(ports[0])
} catch {}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    host: '127.0.0.1',
    proxy: {
      '/status': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/stream': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/wiki': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/memory': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/statusbar/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/overview': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/settings': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/chat': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/logs/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/chart-data': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/brain/state': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/brain/runs': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/brain/events/stream': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/brain/memory': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/gate': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      '/log': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
