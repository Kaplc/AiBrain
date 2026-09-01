import { useEffect } from 'react'
import { NavSidebar } from './components/NavSidebar'
import { ConsolePanel } from './components/ConsolePanel'
import { StatusBar } from './components/StatusBar'
import { ToastHost } from './components/ToastHost'
import { RouterProvider, useRouter } from './router'
import OverviewView from './views/OverviewView'
import MemoryView from './views/MemoryView'
import StreamView from './views/StreamView'
import StatsView from './views/StatsView'
import LogsView from './views/LogsView'
import SettingsView from './views/SettingsView'
import ChatView from './views/ChatView'
import BrainView from './views/BrainView'
import GateView from './views/GateView'
import WikiView from './views/WikiView'

function PageRenderer({ path }: { path: string }) {
  if (path.startsWith('/overview')) return <OverviewView />
  if (path.startsWith('/memory')) return <MemoryView />
  if (path.startsWith('/stream')) return <StreamView />
  if (path.startsWith('/stats')) return <StatsView />
  if (path.startsWith('/logs')) return <LogsView />
  if (path.startsWith('/settings')) return <SettingsView />
  if (path.startsWith('/chat')) return <ChatView />
  if (path.startsWith('/brain')) return <BrainView />
  if (path.startsWith('/gate')) return <GateView />
  if (path.startsWith('/wiki')) return <WikiView />
  return <OverviewView />
}

function Shell() {
  const { reload } = useRouter()

  useEffect(() => {
    function handleGlobalKeydown(e: KeyboardEvent) {
      if (e.key === '`' || e.key === '~') {
        e.preventDefault()
        window.dispatchEvent(new CustomEvent('aibrain:toggle-console'))
      }
      if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
        e.preventDefault()
        reload()
      }
    }
    window.addEventListener('keydown', handleGlobalKeydown)
    return () => window.removeEventListener('keydown', handleGlobalKeydown)
  }, [reload])

  return (
    <>
      <div className="app">
        <NavSidebar />
        <main className="main-content">
          <div id="page-content">
            <PageSlot />
          </div>
          <StatusBar />
        </main>
      </div>
      <ConsolePanel />
      <ToastHost />
    </>
  )
}

/* 消费路由 path 并渲染对应页面（在 Provider 内部） */
function PageSlot() {
  const { path } = useRouter()
  return <PageRenderer path={path} />
}

export default function App() {
  return (
    <RouterProvider>
      <Shell />
    </RouterProvider>
  )
}
