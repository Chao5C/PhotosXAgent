import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import type { LoginForm, User } from '@/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    isAuthenticated: !!localStorage.getItem('auth-token'),
    token: localStorage.getItem('auth-token'),
    refreshToken: localStorage.getItem('refresh-token'),
    user: JSON.parse(localStorage.getItem('user-info') || 'null') as User | null,
    loginLoading: false,
    redirectPath: '/'
  }),
  getters: {
    userDisplayName: (state) => state.user?.username || '用户'
  },
  actions: {
    setAuthInfo(token: string, refreshToken?: string, user?: User) {
      this.token = token
      this.isAuthenticated = true
      if (refreshToken) this.refreshToken = refreshToken
      if (user) this.user = user
      localStorage.setItem('auth-token', token)
      if (refreshToken) localStorage.setItem('refresh-token', refreshToken)
      if (user) localStorage.setItem('user-info', JSON.stringify(user))
    },
    clearAuthInfo() {
      this.token = null
      this.refreshToken = null
      this.user = null
      this.isAuthenticated = false
      localStorage.removeItem('auth-token')
      localStorage.removeItem('refresh-token')
      localStorage.removeItem('user-info')
    },
    async login(form: LoginForm) {
      if (this.loginLoading) return false
      this.loginLoading = true
      try {
        const response = await authApi.login(form)
        if (response.success) {
          this.setAuthInfo(response.data.access_token, response.data.refresh_token, response.data.user)
          return true
        }
        return false
      } catch {
        return false
      } finally {
        this.loginLoading = false
      }
    },
    async logout() {
      try {
        await authApi.logout()
      } catch {
        /* ignore */
      }
      this.clearAuthInfo()
    },
    async checkAuthStatus() {
      if (!this.token) return false
      try {
        const response = await authApi.me()
        if (response.success) {
          this.user = response.data
          this.isAuthenticated = true
          return true
        }
      } catch {
        this.clearAuthInfo()
      }
      return false
    },
    getAndClearRedirectPath() {
      const path = this.redirectPath || '/gallery'
      this.redirectPath = '/'
      return path === '/' ? '/gallery' : path
    },
    setRedirectPath(path: string) {
      this.redirectPath = path
    }
  }
})
