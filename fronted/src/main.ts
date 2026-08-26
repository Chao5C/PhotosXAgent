import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'leaflet/dist/leaflet.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useAppStore } from './stores/app'
import './styles/index.scss'
import './styles/dark-theme.scss'

const app = createApp(App)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

const initApp = async () => {
  const authStore = useAuthStore()
  const appStore = useAppStore()
  appStore.applyTheme()
  await appStore.checkApiConnection()
  if (authStore.token) {
    await authStore.checkAuthStatus()
  }
  app.mount('#app')
}

initApp()
