import { useEffect, useState } from 'react'
import { useRouter } from '../router'
import './NavSidebar.css'

const navItems = [
  { name: 'overview', label: '总览', path: '/overview' },
  { name: 'memory', label: '记忆', path: '/memory' },
  { name: 'chat', label: '对话', path: '/chat' },
  { name: 'brain', label: '大脑', path: '/brain' },
  { name: 'gate', label: 'Gate', path: '/gate' },
  { name: 'stream', label: '流', path: '/stream' },
  { name: 'stats', label: '用量', path: '/stats' },
  { name: 'logs', label: '日志', path: '/logs' },
  { name: 'settings', label: '设置', path: '/settings' },
]

export function NavSidebar() {
  const { path, navigate } = useRouter()

  function openInBrowser() {
    const electronApi = (window as any).electronAPI
    if (electronApi?.openInBrowser) {
      electronApi.openInBrowser()
    } else if ((window as any).pywebview?.api) {
      ;(window as any).pywebview.api.open_in_browser()
    } else {
      window.open(window.location.href, '_blank')
    }
  }

  return (
    <nav className="nav-sidebar">
      <div className="nav-logo" onClick={openInBrowser} title="在浏览器中打开">M</div>
      <div className="nav-items">
        {navItems.map((item) => (
          <button
            key={item.name}
            className={`nav-item${path.startsWith(item.path) ? ' active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
