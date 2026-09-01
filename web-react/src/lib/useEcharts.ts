/* ECharts React 封装 - 等价 Vue 版 useEcharts（init/setOption/dispose/resize） */
import { useEffect, useRef, type RefObject } from 'react'
import * as echarts from 'echarts'

export function useEcharts(containerRef: RefObject<HTMLElement | null>) {
  const instanceRef = useRef<echarts.ECharts | null>(null)

  function init(): boolean {
    if (!containerRef.current) return false
    if (!instanceRef.current) {
      instanceRef.current = echarts.init(containerRef.current)
    }
    return true
  }

  function setOption(option: echarts.EChartsOption) {
    if (init()) instanceRef.current!.setOption(option)
  }

  function clear() {
    instanceRef.current?.clear()
  }

  function resize() {
    instanceRef.current?.resize()
  }

  function dispose() {
    instanceRef.current?.dispose()
    instanceRef.current = null
  }

  useEffect(() => {
    const handleResize = () => {
      setTimeout(() => instanceRef.current?.resize(), 250)
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      dispose()
    }
  }, [])

  return { setOption, clear, resize, getInstance: () => instanceRef.current }
}
