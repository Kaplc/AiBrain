/* 全局 Toast - 等价 Vue 版 useToast（单例状态 + 订阅） */
type ToastType = 'success' | 'error' | 'info'

let listeners: Array<(s: { visible: boolean; message: string; type: ToastType }) => void> = []
let toastState = { visible: false, message: '', type: 'success' as ToastType }
let timer: ReturnType<typeof setTimeout> | null = null

function emit() {
  listeners.forEach((l) => l({ ...toastState }))
}

export function subscribeToast(fn: (s: typeof toastState) => void): () => void {
  listeners.push(fn)
  return () => {
    listeners = listeners.filter((l) => l !== fn)
  }
}

export function getToastState() {
  return toastState
}

export function showToast(msg: string, t: ToastType = 'success') {
  toastState = { visible: true, message: msg, type: t }
  emit()
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    toastState = { ...toastState, visible: false }
    emit()
  }, 2800)
}

export function useToast() {
  return { show: showToast }
}
