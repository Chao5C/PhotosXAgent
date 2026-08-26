import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    theme: (localStorage.getItem('app-theme') as 'light' | 'dark' | 'auto') || 'auto',
    sidebarCollapsed: localStorage.getItem('sidebar-collapsed') === 'true',
    sidebarWidth: 220,
    isOnline: navigator.onLine,
    apiConnected: false
  }),
  getters: {
    isDarkTheme(): boolean {
      if (this.theme === 'auto') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches
      }
      return this.theme === 'dark'
    },
    actualSidebarWidth(): number {
      return this.sidebarCollapsed ? 64 : this.sidebarWidth
    }
  },
  actions: {
    applyTheme() {
      document.documentElement.classList.toggle('dark', this.isDarkTheme)
    },
    toggleTheme() {
      this.theme = this.isDarkTheme ? 'light' : 'dark'
      localStorage.setItem('app-theme', this.theme)
      this.applyTheme()
    },
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem('sidebar-collapsed', String(this.sidebarCollapsed))
    },
    setSidebarCollapsed(collapsed: boolean) {
      this.sidebarCollapsed = collapsed
      localStorage.setItem('sidebar-collapsed', String(collapsed))
    },
    setOnlineStatus(online: boolean) {
      this.isOnline = online
    },
    setApiConnected(connected: boolean) {
      this.apiConnected = connected
    },
    async checkApiConnection() {
      try {
        const response = await fetch('/api/health', { signal: AbortSignal.timeout(3000) })
        const connected = response.ok
        this.apiConnected = connected
        return connected
      } catch {
        this.apiConnected = false
        return false
      }
    }
  }
})
