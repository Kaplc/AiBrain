/* 极简路由 - 兼容 Vue 版路由语义（history API + popstate） */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type RouterCtx = {
  path: string
  navigate: (to: string) => void
  reload: () => void
}

const Ctx = createContext<RouterCtx | null>(null)

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(() => window.location.pathname || '/')

  useEffect(() => {
    // 默认重定向到 /overview
    if (path === '/' || path === '') {
      window.history.replaceState({}, '', '/overview')
      setPath('/overview')
    }
  }, [path])

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = (to: string) => {
    window.history.pushState({}, '', to)
    setPath(to)
  }

  const reload = () => window.location.reload()

  return <Ctx.Provider value={{ path, navigate, reload }}>{children}</Ctx.Provider>
}

export function useRouter(): RouterCtx {
  const ctx = useContext(Ctx)
  if (!ctx) {
    // 未包裹 RouterProvider 时回退为只读模式（直接读 location，不参与导航）
    return {
      path: window.location.pathname || '/',
      navigate: (to: string) => { window.history.pushState({}, '', to) },
      reload: () => window.location.reload(),
    }
  }
  return ctx
}
