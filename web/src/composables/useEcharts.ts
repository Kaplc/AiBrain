import { onMounted, onUnmounted, onActivated, type Ref } from 'vue'
import * as echarts from 'echarts'

export function useEcharts(containerRef: Ref<HTMLElement | null>) {
  let instance: echarts.ECharts | null = null
  let resizeTimer: ReturnType<typeof setTimeout> | null = null
  let lastContainer: HTMLElement | null = null

  function init(): boolean {
    if (!containerRef.value) return false
    // 如果容器变了，需要重新初始化
    if (instance && lastContainer !== containerRef.value) {
      instance.dispose()
      instance = null
    }
    if (!instance) {
      instance = echarts.init(containerRef.value)
      lastContainer = containerRef.value
    }
    return true
  }

  function setOption(option: echarts.EChartsOption) {
    if (init()) {
      instance!.setOption(option)
    }
  }

  function dispose() {
    if (instance) {
      instance.dispose()
      instance = null
      lastContainer = null
    }
  }

  function handleResize() {
    if (resizeTimer) clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => instance?.resize(), 250)
  }

  onMounted(() => {
    window.addEventListener('resize', handleResize)
  })

  onActivated(() => {
    // 组件激活时尝试重新初始化（容器可能变了）
    init()
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    dispose()
  })

  return { setOption, dispose, getInstance: () => instance }
}
