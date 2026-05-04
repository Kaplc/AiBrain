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
      path: '/wiki',
      name: 'wiki',
      component: () => import('@/views/WikiView/WikiView.vue'),
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
  ],
})

export default router
