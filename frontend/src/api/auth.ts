import { ApiClient } from './request'
import type { LoginForm, LoginResponse, User } from '@/types'

export const authApi = {
  login: (data: LoginForm) =>
    ApiClient.post<LoginResponse>('/api/auth/login', data, { skipAuth: true, skipAuthError: true }),
  logout: () => ApiClient.post('/api/auth/logout'),
  me: () => ApiClient.get<User>('/api/auth/me'),
  refresh: (refresh_token: string) => ApiClient.post('/api/auth/refresh', { refresh_token })
}
