import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

export interface ApiResponse<T = any> {
  success: boolean
  data: T
  message: string
  code?: number
}

export interface RequestConfig extends AxiosRequestConfig {
  skipAuth?: boolean
  skipAuthError?: boolean
  skipErrorHandler?: boolean
}

let isHandling401 = false

const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '',
    timeout: 60000
  })

  instance.interceptors.request.use((config: any) => {
    const authStore = useAuthStore()
    if (!config.skipAuth && authStore.token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  })

  instance.interceptors.response.use(
    (response: AxiosResponse) => {
      const data = response.data
      if (data && typeof data.success === 'boolean' && !data.success) {
        ElMessage.error(data.message || '请求失败')
        return Promise.reject(new Error(data.message || '请求失败'))
      }
      return data
    },
    async (error) => {
      const authStore = useAuthStore()
      const config = error.config as RequestConfig
      const status = error.response?.status
      if (status === 401 && !config?.skipAuthError) {
        if (!isHandling401) {
          isHandling401 = true
          authStore.clearAuthInfo()
          router.push('/login')
          ElMessage.error('登录已过期，请重新登录')
          setTimeout(() => {
            isHandling401 = false
          }, 2000)
        }
      } else if (!config?.skipErrorHandler) {
        const message = error.response?.data?.detail || error.response?.data?.message || error.message || '请求失败'
        ElMessage.error(typeof message === 'string' ? message : '请求失败')
      }
      return Promise.reject(error)
    }
  )

  return instance
}

const request = createAxiosInstance()

export class ApiClient {
  static get<T = any>(url: string, params?: any, config?: RequestConfig) {
    return request.get(url, { params, ...config }) as Promise<ApiResponse<T>>
  }
  static post<T = any>(url: string, data?: any, config?: RequestConfig) {
    return request.post(url, data, config) as Promise<ApiResponse<T>>
  }
  static put<T = any>(url: string, data?: any, config?: RequestConfig) {
    return request.put(url, data, config) as Promise<ApiResponse<T>>
  }
  static patch<T = any>(url: string, data?: any, config?: RequestConfig) {
    return request.patch(url, data, config) as Promise<ApiResponse<T>>
  }
  static delete<T = any>(url: string, config?: RequestConfig) {
    return request.delete(url, config) as Promise<ApiResponse<T>>
  }
}

export default request
