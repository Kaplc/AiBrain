import { useEffect, useState } from 'react'
import { fetchJson, postJson } from '../lib/api'
import { useToast } from '../lib/useToast'
import './SettingsView.css'

/* 模型 Tab */
function ModelTab() {
  const [pendingDevice, setPendingDevice] = useState('cpu')
  const [savedDevice, setSavedDevice] = useState('cpu')
  const [desc, setDesc] = useState('')
  const [gpuInfo, setGpuInfo] = useState<{ html: string; cls: string }>({ html: '检测中...', cls: 'ok' })
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  async function load() {
    try {
      const [cfg, st] = await Promise.all([
        fetchJson<any>('/settings/api'),
        fetchJson<any>('/statusbar/api'),
      ])
      const device = cfg.device ?? 'cpu'
      setPendingDevice(device)
      setSavedDevice(device)
      const modelName = st.embedding_model || 'BAAI/bge-m3'
      const dim = st.embedding_dim || 1024
      setDesc(`${modelName} · 向量维度 ${dim}`)
      if (st.cuda_available) {
        setGpuInfo({ html: `✅ 检测到 GPU：<strong>${st.gpu_name}</strong>`, cls: 'ok' })
      } else if (st.gpu_hardware) {
        setGpuInfo({
          html: '⚠️ 检测到 NVIDIA GPU，但安装的是 CPU 版 PyTorch。<br><small>运行以下命令安装 GPU 版：</small><br><code>pip uninstall torch -y && pip install torch --index-url https://download.pytorch.org/whl/cu124</code>',
          cls: 'warn',
        })
      } else {
        setGpuInfo({ html: '未检测到 NVIDIA GPU，GPU 选项不可用', cls: 'err' })
      }
    } catch { /* ignore */ }
  }

  useEffect(() => { load() }, [])

  async function apply() {
    if (pendingDevice === savedDevice) { toast.show('设置未变更', 'info'); return }
    setSaving(true)
    try {
      await postJson('/settings/reload-model', { device: pendingDevice })
      setSavedDevice(pendingDevice)
      toast.show(`✅ 已保存并重载模型（${pendingDevice}）`)
    } catch (e: any) {
      toast.show('保存失败: ' + e, 'error')
    }
    setSaving(false)
  }

  return (
    <div className="settings-panel">
      <div className="setting-group">
        <div className="setting-label">嵌入模型</div>
        <div className="setting-desc">{desc || '加载中...'}</div>
      </div>
      <div className="setting-group">
        <div className="setting-label">运行设备</div>
        <div className="device-options">
          <label className="device-option">
            <input type="radio" name="device" checked={pendingDevice === 'cpu'} onChange={() => setPendingDevice('cpu')} />
            <span>CPU</span>
          </label>
          <label className="device-option">
            <input type="radio" name="device" checked={pendingDevice === 'cuda'} onChange={() => setPendingDevice('cuda')} />
            <span>GPU (CUDA)</span>
          </label>
        </div>
        <div className={`gpu-info ${gpuInfo.cls}`} dangerouslySetInnerHTML={{ __html: gpuInfo.html }} />
      </div>
      <div className="setting-actions">
        <button className="btn-secondary" onClick={() => { setPendingDevice(savedDevice); toast.show('已重置', 'info') }}>重置</button>
        <button className="btn-accent" onClick={apply} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
      </div>
    </div>
  )
}

/* LLM Tab */
function LLMTab() {
  const [fields, setFields] = useState<any[]>([])
  const [values, setValues] = useState<Record<string, any>>({})
  const [defaults, setDefaults] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  async function load() {
    try {
      const aibrain = await fetchJson<any>('/settings/aibrain-config')
      const section = aibrain?.llm
      if (section?.fields) {
        setFields(section.fields)
        const v: Record<string, any> = {}
        const d: Record<string, any> = {}
        for (const f of section.fields) {
          v[f.key] = f.value ?? ''
          d[f.key] = f.default ?? ''
        }
        setValues(v)
        setDefaults(d)
      }
    } catch { /* ignore */ }
  }

  useEffect(() => { load() }, [])

  async function save() {
    if (!fields.length) return
    setSaving(true)
    try {
      const data: Record<string, any> = {}
      for (const f of fields) {
        const raw = values[f.key] ?? ''
        data[f.key] = f.type === 'number' ? (parseFloat(raw) || 0) : raw
      }
      const r = await postJson<any>('/settings/save-aibrain-config', { llm: data })
      if (r?.error) toast.show('保存失败: ' + r.error, 'error')
      else toast.show('✅ llm.json 已保存')
    } catch (e: any) {
      toast.show('保存失败: ' + e, 'error')
    }
    setSaving(false)
  }

  function reset() {
    const v: Record<string, any> = {}
    for (const f of fields) v[f.key] = f.default ?? ''
    setValues(v)
    toast.show('已恢复默认', 'info')
  }

  return (
    <div className="settings-panel">
      {fields.map((f) => (
        <div className="setting-group" key={f.key}>
          <div className="setting-label">{f.label || f.key}</div>
          {f.type === 'select' && f.options ? (
            <select
              className="setting-select"
              value={values[f.key] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            >
              {f.options.map((opt: string) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          ) : f.type === 'dir' ? (
            <input
              className="setting-input"
              type="text"
              value={values[f.key] ?? ''}
              placeholder={f.placeholder}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          ) : (
            <input
              className="setting-input"
              type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'}
              value={values[f.key] ?? ''}
              placeholder={f.placeholder}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          )}
        </div>
      ))}
      {fields.length === 0 && <div className="empty-state">配置加载中...</div>}
      <div className="setting-actions">
        <button className="btn-secondary" onClick={reset}>恢复默认</button>
        <button className="btn-accent" onClick={save} disabled={saving}>{saving ? '保存中...' : '保存'}</button>
      </div>
    </div>
  )
}

/* 统计 Tab */
function StatsTab() {
  const [status, setStatus] = useState<any>(null)

  useEffect(() => {
    fetchJson<any>('/overview/db-status').then(setStatus).catch(() => {})
  }, [])

  return (
    <div className="settings-panel">
      <div className="setting-group">
        <div className="setting-label">统计数据库状态</div>
        <div className="setting-desc">
          {status ? (status.ok ? '✅ 正常' : `❌ ${status.error}`) : '加载中...'}
        </div>
      </div>
      {status?.ok && status.stats && (
        <pre className="stats-pre">{JSON.stringify(status.stats, null, 2)}</pre>
      )}
    </div>
  )
}

const TABS = [
  { key: 'model', label: '模型' },
  { key: 'llm', label: 'LLM' },
  { key: 'stats', label: '统计' },
]

export default function SettingsView() {
  const [activeTab, setActiveTab] = useState('model')

  return (
    <div className="settings-page">
      <div className="page-header"><div className="page-title">设置</div></div>
      <div className="settings-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`settings-tab${activeTab === t.key ? ' active' : ''}`} onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      {activeTab === 'model' && <ModelTab />}
      {activeTab === 'llm' && <LLMTab />}
      {activeTab === 'stats' && <StatsTab />}
    </div>
  )
}
