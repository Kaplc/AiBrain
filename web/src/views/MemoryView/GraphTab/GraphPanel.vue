<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { memoryViewModel } from '../index'
import ForceGraph from 'force-graph'
import { useApi } from '@/composables/useApi'

const vm = memoryViewModel
const api = useApi()
const containerRef = ref<HTMLDivElement | null>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let graph: any = null
let resizeObserver: ResizeObserver | null = null

// 状态管理
const showLabels = ref(true)
const showParticles = ref<boolean | null>(null) // null = 未加载，onMounted 从后端读取

async function loadAnimationState() {
  try {
    const res = await api.fetchJson<{ showGraphAnimation: boolean }>('/memory/settings')
    showParticles.value = res.showGraphAnimation
  } catch {
    showParticles.value = true // 读取失败默认开启
  }
}

async function handleAnimationToggle() {
  if (showParticles.value === null) return
  const newValue = !showParticles.value
  showParticles.value = newValue
  // 重建图谱应用粒子数量变化
  if (graph) buildGraph()
  // 持久化到后端
  try {
    await api.postJson('/memory/settings', { showGraphAnimation: newValue })
  } catch {
    // 静默失败，用户已经看到效果
  }
}

// 星空背景
type Star = { x: number; y: number; r: number; base: number; phase: number; speed: number }
let stars: Star[] = []

function generateStars(w: number, h: number) {
  stars = Array.from({ length: 280 }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    r: 0.25 + Math.random() * 1.1,
    base: 0.12 + Math.random() * 0.65,
    phase: Math.random() * Math.PI * 2,
    speed: 0.25 + Math.random() * 1.1,
  }))
}

// 节点颜色
// 固定类型颜色（锚点节点）
const typeColors: Record<string, string> = {
  user: '#5B8FF9',  // 蓝
  self: '#F6BD16',  // 金黄
  rule: '#E86452',  // 珊瑚
  exp:  '#6DC8EC',  // 天蓝
}

// concept 节点：按连接数冷→暖渐变（热力色温）
// 0% 冷蓝 33% 青绿 66% 琥珀 100% 玫瑰
const heatStops: Array<[number, number, number]> = [
  [100, 140, 255],  // 冷蓝  低连接
  [ 56, 211, 159],  // 青绿
  [251, 191,  36],  // 琥珀
  [249, 115, 148],  // 玫瑰 高连接
]

function lerpHeat(t: number): string {
  // t in [0,1]，在 heatStops 上分段线性插值
  const n  = heatStops.length - 1
  const fi = Math.min(t * n, n - 0.0001)
  const i  = Math.floor(fi)
  const f  = fi - i
  const a  = heatStops[i], b = heatStops[i + 1]
  const r  = Math.round(a[0] + (b[0] - a[0]) * f)
  const g  = Math.round(a[1] + (b[1] - a[1]) * f)
  const bl = Math.round(a[2] + (b[2] - a[2]) * f)
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${bl.toString(16).padStart(2,'0')}`
}

// hex 转 [r,g,b]
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)]
}

// 构建图谱
function buildGraph() {
  if (!containerRef.value) return
  const data = vm.graphTab.graphData.value
  if (!data.nodes.length) return

  if (graph) { graph._destructor(); graph = null }

  const width  = Math.max(containerRef.value.clientWidth,  300)
  const height = Math.max(containerRef.value.clientHeight, 400)
  generateStars(width, height)

  // 统计每个节点的连接度（边数）
  const degree: Record<string, number> = {}
  for (const e of data.edges) {
    degree[e.source] = (degree[e.source] || 0) + 1
    degree[e.target] = (degree[e.target] || 0) + 1
  }
  const degrees = Object.values(degree)
  const maxDeg  = Math.max(1, ...degrees)

  const nodes = data.nodes.map(n => {
    let color: string
    if (typeColors[n.type]) {
      color = typeColors[n.type]
    } else {
      // concept：按连接数归一化到 [0,1]，映射到热力色温
      const t = (degree[n.id] || 0) / maxDeg
      color = lerpHeat(t)
    }
    return { id: n.id, label: n.label, val: Math.max(1, n.memoryCount), color }
  })

  const links = data.edges.map(e => ({
    source: e.source,
    target: e.target,
    speed: 0.0003 + Math.random() * 0.0008,
  }))

  graph = ForceGraph()(containerRef.value)
    .graphData({ nodes, links })
    .width(width)
    .height(height)
    .backgroundColor('#020510')
    .nodeId('id')
    .nodeLabel('')           // 关闭内置 tooltip，用自绘标签
    .nodeVal('val')
    .nodeColor('color')
    .nodeRelSize(1)

    // 背景星空
    .onRenderFramePre((ctx: CanvasRenderingContext2D) => {
      const canvas = ctx.canvas
      const dpr = window.devicePixelRatio || 1
      const w = canvas.width / dpr
      const h = canvas.height / dpr
      ctx.save()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const t = Date.now() / 1000
      for (const s of stars) {
        const opacity = s.base * (0.55 + 0.45 * Math.sin(t * s.speed + s.phase))
        // 大星加十字衍射
        if (s.r > 1.0) {
          ctx.save()
          ctx.strokeStyle = `rgba(200,220,255,${opacity * 0.5})`
          ctx.lineWidth = 0.5
          ctx.beginPath(); ctx.moveTo(s.x - s.r * 3, s.y); ctx.lineTo(s.x + s.r * 3, s.y); ctx.stroke()
          ctx.beginPath(); ctx.moveTo(s.x, s.y - s.r * 3); ctx.lineTo(s.x, s.y + s.r * 3); ctx.stroke()
          ctx.restore()
        }
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(200,220,255,${opacity})`
        ctx.fill()
      }
      // 星云晕染（左侧 + 右下两团）
      const nebula1 = ctx.createRadialGradient(w * 0.2, h * 0.25, 0, w * 0.2, h * 0.25, w * 0.28)
      nebula1.addColorStop(0, 'rgba(80,60,160,0.06)')
      nebula1.addColorStop(1, 'transparent')
      ctx.fillStyle = nebula1; ctx.fillRect(0, 0, w, h)

      const nebula2 = ctx.createRadialGradient(w * 0.78, h * 0.7, 0, w * 0.78, h * 0.7, w * 0.22)
      nebula2.addColorStop(0, 'rgba(30,100,160,0.05)')
      nebula2.addColorStop(1, 'transparent')
      ctx.fillStyle = nebula2; ctx.fillRect(0, 0, w, h)
      ctx.restore()
    })

    // 连线
    .linkColor(() => 'rgba(100,160,255,0.18)')
    .linkWidth(0.7)
    .linkDirectionalParticles(showParticles.value !== false ? 2 : 0)
    .linkDirectionalParticleWidth(1.8)
    .linkDirectionalParticleSpeed((link: any) => link.speed)
    .linkDirectionalParticleCanvasObject((x: number, y: number, link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const photons: any[] = link.__photons || []
      let progress = 0.5
      const src = typeof link.source === 'object' ? link.source : { x: 0, y: 0 }
      const tgt = typeof link.target === 'object' ? link.target : { x: 0, y: 0 }
      if (photons.length) {
        let minDist = Infinity
        for (const p of photons) {
          const r = p.__progressRatio ?? 0.5
          const px = src.x + (tgt.x - src.x) * r
          const py = src.y + (tgt.y - src.y) * r
          const d  = (px - x) ** 2 + (py - y) ** 2
          if (d < minDist) { minDist = d; progress = r }
        }
      }

      // 颜色插值
      const srcColor = (src.color) || '#8ED6FF'
      const tgtColor = (tgt.color) || '#8ED6FF'
      const [r1, g1, b1] = hexToRgb(srcColor)
      const [r2, g2, b2] = hexToRgb(tgtColor)
      const rv = Math.round(r1 + (r2 - r1) * progress)
      const gv = Math.round(g1 + (g2 - g1) * progress)
      const bv = Math.round(b1 + (b2 - b1) * progress)

      // 连线方向角度
      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const angle = Math.atan2(dy, dx)

      // 梭形尺寸：半长轴（沿连线方向）、半短轴（垂直方向）
      const halfLen = Math.max(2.5, 6 / Math.sqrt(globalScale))
      const halfW   = Math.max(0.3, 0.7 / Math.sqrt(globalScale))

      ctx.save()
      ctx.translate(x, y)
      ctx.rotate(angle)

      // 梭形渐变：头部亮、尾部透明（尾部朝 source 方向）
      const grad = ctx.createLinearGradient(-halfLen, 0, halfLen, 0)
      grad.addColorStop(0,   `rgba(${rv},${gv},${bv},0)`)       // 尾（来源方向）透明
      grad.addColorStop(0.4, `rgba(${rv},${gv},${bv},0.55)`)
      grad.addColorStop(1,   `rgba(${rv},${gv},${bv},0.95)`)    // 头（目标方向）亮

      // 用 ellipse 画梭形（圆角纺锤）
      ctx.beginPath()
      ctx.ellipse(0, 0, halfLen, halfW, 0, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()

      // 头部亮点（小圆，增强导弹感）
      ctx.beginPath()
      ctx.arc(halfLen * 0.7, 0, halfW * 0.8, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${rv},${gv},${bv},0.95)`
      ctx.fill()

      ctx.restore()
    })

    // 节点：多层光晕
    .nodeCanvasObject((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      if (node.x == null || node.y == null) return
      const size  = Math.sqrt(Math.max(1, node.val)) * 0.4 + 4
      const color = node.color || '#945FB9'
      const [nr, ng, nb] = hexToRgb(color)
      const rgb = `${nr},${ng},${nb}`

      // 圈1：超大弥散晕
      const g1 = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, size * 5)
      g1.addColorStop(0, `rgba(${rgb},0.08)`)
      g1.addColorStop(1, 'transparent')
      ctx.beginPath(); ctx.arc(node.x, node.y, size * 5, 0, Math.PI * 2)
      ctx.fillStyle = g1; ctx.fill()

      // 圈2：中光晕
      const g2 = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, size * 2.5)
      g2.addColorStop(0, `rgba(${rgb},0.25)`)
      g2.addColorStop(1, 'transparent')
      ctx.beginPath(); ctx.arc(node.x, node.y, size * 2.5, 0, Math.PI * 2)
      ctx.fillStyle = g2; ctx.fill()

      // 圈3：冠冕
      ctx.beginPath(); ctx.arc(node.x, node.y, size * 1.45, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${rgb},0.35)`; ctx.fill()

      // 圈4：实体核心（径向渐变，中心亮）
      const g4 = ctx.createRadialGradient(node.x - size * 0.2, node.y - size * 0.2, 0, node.x, node.y, size)
      g4.addColorStop(0, `rgba(${Math.min(255, nr + 60)},${Math.min(255, ng + 60)},${Math.min(255, nb + 60)},1)`)
      g4.addColorStop(1, `rgba(${nr},${ng},${nb},1)`)
      ctx.beginPath(); ctx.arc(node.x, node.y, size, 0, Math.PI * 2)
      ctx.fillStyle = g4; ctx.fill()

      // Label (toggleable)
      if (showLabels.value) {
        const label    = String(node.label || node.id || '')
        const fontSize = Math.min(13, Math.max(7, 11 / globalScale))
        ctx.font         = `${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
        ctx.textAlign    = 'center'
        ctx.textBaseline = 'top'
        ctx.shadowColor  = color
        ctx.shadowBlur   = 6
        ctx.fillStyle    = 'rgba(220,235,255,0.92)'
        ctx.fillText(label, node.x, node.y + size * 1.5 + 1)
        ctx.shadowBlur = 0
      }
    })
    .nodeCanvasObjectMode(() => 'replace')
    .nodePointerAreaPaint((node: any, color: string, ctx: CanvasRenderingContext2D) => {
      if (node.x == null || node.y == null) return
      const size = Math.sqrt(Math.max(1, node.val)) * 0.4 + 4
      ctx.beginPath(); ctx.arc(node.x, node.y, size, 0, Math.PI * 2)
      ctx.fillStyle = color; ctx.fill()
    })

    .enablePanInteraction(false)
    .d3AlphaDecay(0.008)
    .d3VelocityDecay(0.35)
    .warmupTicks(100)
    .cooldownTicks(200)
    .onEngineStop(() => { if (graph) graph.zoomToFit(600, 40) })

  // 动态连线长度
  const nodeValMap: Record<string, number> = {}
  nodes.forEach(n => { nodeValMap[n.id] = n.val })
  graph.d3Force('link').distance((link: any) => {
    const sv = nodeValMap[typeof link.source === 'object' ? link.source.id : link.source] ?? 1
    const tv = nodeValMap[typeof link.target === 'object' ? link.target.id : link.target] ?? 1
    return (Math.sqrt(Math.max(1, sv)) * 0.4 + 4 + Math.sqrt(Math.max(1, tv)) * 0.4 + 4) * 4 + 30
  })

  setupRightClickPan()
}

// 右键平移
function setupRightClickPan() {
  const container = containerRef.value
  if (!container) return
  const canvas = container.querySelector('canvas')
  if (!canvas) return

  canvas.addEventListener('contextmenu', e => e.preventDefault())

  let isPanning = false, lastX = 0, lastY = 0

  canvas.addEventListener('mousedown', e => {
    if (e.button !== 2) return
    isPanning = true; lastX = e.clientX; lastY = e.clientY
    canvas.style.cursor = 'grabbing'; e.preventDefault()
  })
  window.addEventListener('mousemove', e => {
    if (!isPanning || !graph) return
    const dx = e.clientX - lastX, dy = e.clientY - lastY
    lastX = e.clientX; lastY = e.clientY
    const z = graph.zoom(), c = graph.centerAt()
    graph.centerAt(c.x - dx / z, c.y - dy / z)
  })
  window.addEventListener('mouseup', e => {
    if (e.button !== 2) return
    isPanning = false; canvas.style.cursor = ''
  })
}

// 侦听
watch(() => vm.graphTab.graphData.value, () => {
  if (vm.currentTab.value === 'graph') setTimeout(buildGraph, 150)
})
watch(() => vm.currentTab.value, tab => {
  if (tab === 'graph') setTimeout(() => {
    if (vm.graphTab.graphData.value.nodes.length) buildGraph()
  }, 150)
})

onMounted(() => {
  loadAnimationState() // 从后端加载动画开关状态
  if (vm.currentTab.value === 'graph') {
    if (!vm.graphTab.graphData.value.nodes.length) vm.graphTab.loadGraph()
    else setTimeout(buildGraph, 150)
  }
  resizeObserver = new ResizeObserver(entries => {
    const { width, height } = entries[0].contentRect
    if (width > 0 && height > 0) {
      generateStars(width, height)
      if (graph) graph.width(width).height(height)
    }
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect(); resizeObserver = null
  if (graph) { graph._destructor(); graph = null }
})

function handleRefresh() { vm.graphTab.loadGraph() }
</script>

<template>
  <div class="graph-panel">
    <div class="graph-toolbar">
      <span class="graph-info">
        节点: {{ vm.graphTab.graphData.value.nodes.length }} |
        关系: {{ vm.graphTab.graphData.value.edges.length }}
      </span>
      <button class="btn-toggle" :class="{ active: showLabels }" @click="showLabels = !showLabels" title="Show/Hide Labels">标</button>
      <button class="btn-toggle" :class="{ active: showParticles }" @click="handleAnimationToggle" title="Show/Hide Animation">动</button>
      <button class="btn-refresh" @click="handleRefresh" :disabled="vm.graphTab.loading.value">
        {{ vm.graphTab.loading.value ? '加载中...' : '刷新' }}
      </button>
    </div>
    <div v-if="vm.graphTab.loading.value" class="graph-loading">加载图谱数据...</div>
    <div v-else-if="!vm.graphTab.graphData.value.nodes.length" class="graph-empty">暂无图谱数据</div>
    <div ref="containerRef" class="graph-container"></div>
  </div>
</template>

<style scoped>
.graph-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(100, 120, 200, 0.15);
  flex-shrink: 0;
  background: rgba(2, 5, 16, 0.6);
  backdrop-filter: blur(8px);
}
.graph-info {
  font-size: 12px;
  color: rgba(140, 170, 220, 0.7);
  letter-spacing: 0.05em;
}
.btn-refresh {
  padding: 4px 14px;
  border: 1px solid rgba(100, 140, 220, 0.25);
  border-radius: 6px;
  background: rgba(30, 50, 100, 0.3);
  color: rgba(140, 170, 220, 0.8);
  cursor: pointer;
  font-size: 12px;
  letter-spacing: 0.05em;
  transition: all 0.2s;
}
.btn-refresh:hover {
  background: rgba(60, 90, 180, 0.35);
  color: #c8d8f0;
  border-color: rgba(100, 160, 255, 0.45);
  box-shadow: 0 0 10px rgba(80, 130, 255, 0.2);
}
.btn-refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-toggle {
  padding: 4px 10px;
  border: 1px solid rgba(100, 140, 220, 0.25);
  border-radius: 6px;
  background: rgba(30, 50, 100, 0.3);
  color: rgba(140, 170, 220, 0.8);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s;
}
.btn-toggle:hover {
  background: rgba(60, 90, 180, 0.35);
  color: #c8d8f0;
}
.btn-toggle.active {
  background: rgba(80, 140, 255, 0.25);
  border-color: rgba(100, 160, 255, 0.5);
  color: #fff;
}
.graph-container {
  flex: 1;
  min-height: 400px;
  background: #020510;
  border-radius: 8px;
  overflow: hidden;
}
.graph-loading, .graph-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(100, 130, 180, 0.5);
  font-size: 13px;
  letter-spacing: 0.1em;
}
</style>