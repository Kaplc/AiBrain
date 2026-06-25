import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/overview',
    },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('@/views/OverviewView/OverviewView.vue'),
    },
    {
      path: '/memory',
      name: 'memory',
      component: () => import('@/views/MemoryView/MemoryView.vue'),
    },
    {
      path: '/stream',
      name: 'stream',
      component: () => import('@/views/StreamView/StreamView.vue'),
    },
    {
      path: '/stats',
      name: 'stats',
      component: () => import('@/views/StatsView/StatsView.vue'),
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/LogsView/LogsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView/SettingsView.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView/ChatView.vue'),
    },
    {
      path: '/brain',
      name: 'brain',
      component: () => import('@/views/BrainView/BrainView.vue'),
    },
    {
      path: '/gate',
      name: 'gate',
      component: () => import('@/views/GateView/GateView.vue'),
    },
  ],
})

export default router
