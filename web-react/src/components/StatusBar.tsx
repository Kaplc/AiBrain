import { useEffect, useState } from 'react'
import { fetchJson } from '../lib/api'
import './StatusBar.css'

interface StatusData {
  model_loaded?: boolean
  qdrant_ready?: boolean
  device?: string
}

export function StatusBar() {
  const [modelLoaded, setModelLoaded] = useState(false)
  const [qdrantReady, setQdrantReady] = useState(false)
  const [device, setDevice] = useState('cpu')
  const [building, setBuilding] = useState(false)
  const [buildMsg, setBuildMsg] = useState('')
  const [buildFailed, setBuildFailed] = useState(false)
  const [buildId, setBuildId] = useState('')
  const [pollTimer, setPollTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  async function fetchStatus() {
    try {
      const d = await fetchJson<StatusData>('/statusbar/api')
      setModelLoaded(!!d.model_loaded)
      setQdrantReady(!!d.qdrant_ready)
      setDevice(d.device ?? 'cpu')
    } catch {
      /* 保持上次状态 */
    }
  }

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 3000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => () => { if (pollTimer) clearTimeout(pollTimer) }, [pollTimer])

  async function pollBuildStatus(id: string) {
    if (!id) return
    try {
      const res = await fetch(`/overview/frontend/build/status?build_id=${id}`)
      const data = await res.json()
      if (data.status === 'done') {
        setBuildMsg('构建成功')
        setBuildFailed(false)
        setBuilding(false)
        setTimeout(() => {
          setBuildMsg('')
          setTimeout(() => window.location.reload(), 300)
        }, 2000)
      } else if (data.status === 'failed') {
        setBuildMsg('构建失败')
        setBuildFailed(true)
        setBuilding(false)
      } else {
        setPollTimer(setTimeout(() => pollBuildStatus(id), 500))
      }
    } catch {
      setBuildMsg('构建失败')
      setBuildFailed(true)
      setBuilding(false)
    }
  }

  async function triggerBuild() {
    if (building) return
    setBuilding(true)
    setBuildMsg('构建中...')
    setBuildFailed(false)
    setBuildId('')
    try {
      const res = await fetch('/overview/frontend/build', { method: 'POST' })
      const data = await res.json()
      if (data.build_id) {
        setBuildId(data.build_id)
        pollBuildStatus(data.build_id)
      } else {
        setBuildMsg('构建失败')
        setBuildFailed(true)
        setBuilding(false)
      }
    } catch {
      setBuildMsg('构建失败')
      setBuildFailed(true)
      setBuilding(false)
    }
  }

  return (
    <div className="statusbar">
      <div className="statusbar-item">
        <span>{modelLoaded ? '模型就绪' : '模型加载中'}</span>
        <div className={`statusbar-dot ${modelLoaded ? 'ok' : 'loading'}`} />
      </div>
      <div className="statusbar-item">
        <span>Qdrant</span>
        <div className={`statusbar-dot ${qdrantReady ? 'ok' : 'err'}`} />
      </div>
      <div className="statusbar-item">
        <span>{device === 'cuda' ? 'GPU' : 'CPU'}</span>
      </div>
      <div className="statusbar-right">
        {buildMsg ? (
          <span className={`build-msg ${buildFailed ? 'fail' : ''} ${building ? 'building' : ''}`}>{buildMsg}</span>
        ) : (
          <button className="build-btn" onClick={triggerBuild} title="构建前端">构建</button>
        )}
      </div>
    </div>
  )
}
