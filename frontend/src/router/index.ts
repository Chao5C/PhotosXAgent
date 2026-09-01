import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

NProgress.configure({ showSpinner: false })

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Auth/Login.vue'),
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/gallery',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'gallery',
        name: 'Gallery',
        component: () => import('@/views/Gallery/index.vue'),
        meta: { title: '图库' }
      },
      {
        path: 'photo/:id',
        name: 'PhotoDetail',
        component: () => import('@/views/Gallery/Detail.vue'),
        meta: { title: '照片详情' }
      },
      {
        path: 'albums',
        name: 'Albums',
        component: () => import('@/views/Albums/index.vue'),
        meta: { title: '相册' }
      },
      {
        path: 'albums/:id',
        name: 'AlbumDetail',
        component: () => import('@/views/Albums/Detail.vue'),
        meta: { title: '相册详情' }
      },
      {
        path: 'journey',
        name: 'Journey',
        component: () => import('@/views/Journey/index.vue'),
        meta: { title: '行程模拟' }
      },
      {
        path: 'recommendations',
        name: 'Recommendations',
        component: () => import('@/views/Recommendations/index.vue'),
        meta: { title: '推荐建议' }
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/Chat/index.vue'),
        meta: { title: '助手' }
      },
      {
        path: 'posters',
        name: 'Posters',
        component: () => import('@/views/Posters/index.vue'),
        meta: { title: '海报图库' }
      },
      {
        path: 'studio',
        name: 'Studio',
        component: () => import('@/views/Studio/index.vue'),
        meta: { title: '自媒体工作台' }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings/index.vue'),
        meta: { title: '设置' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/Error/404.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, _from, next) => {
  NProgress.start()
  document.title = `${to.meta.title || 'PhotosXAgent'} - PhotosXAgent`
  const authStore = useAuthStore()
  if (to.meta.requiresAuth === false) {
    next()
    return
  }
  if (!authStore.isAuthenticated) {
    authStore.setRedirectPath(to.fullPath)
    ElMessage.warning('请先登录')
    next('/login')
    return
  }
  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
