import { onUnmounted } from 'vue'

export function usePolling(callback: () => void, interval: number, jitter = 200) {
  let timer: number | null = null
  let initialTimer: number | null = null

  function start() {
    if (timer !== null) return
    timer = window.setInterval(callback, interval)
    // 随机初始延迟，让多个轮询的触发时刻错开，避免同时请求
    const delay = Math.random() * jitter
    initialTimer = window.setTimeout(callback, delay)
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    if (initialTimer !== null) {
      clearTimeout(initialTimer)
      initialTimer = null
    }
  }

  onUnmounted(stop)

  return { start, stop }
}
