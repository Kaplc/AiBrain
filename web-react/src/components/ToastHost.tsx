import { useSyncExternalStore } from 'react'
import { subscribeToast, getToastState } from '../lib/useToast'

export function ToastHost() {
  const state = useSyncExternalStore(subscribeToast, getToastState, getToastState)
  return (
    <div className={`toast ${state.type}${state.visible ? ' show' : ''}`}>{state.message}</div>
  )
}
