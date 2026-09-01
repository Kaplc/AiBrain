/* 轮询 hook - 等价 Vue 版 usePolling（随机初始延迟错开请求） */
import { useEffect, useRef } from 'react'

export function usePolling(callback: () => void, interval: number, deps: any[] = []) {
  const cbRef = useRef(callback)
  cbRef.current = callback

  useEffect(() => {
    const delay = Math.random() * 200
    const initialTimer = setTimeout(() => cbRef.current(), delay)
    const timer = setInterval(() => cbRef.current(), interval)
    return () => {
      clearTimeout(initialTimer)
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
