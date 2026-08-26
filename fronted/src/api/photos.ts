import { ApiClient } from './request'
import type { Album, ChatMessage, JourneyPoint, Photo, Recommendation } from '@/types'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

export const photoApi = {
  list: (params?: Record<string, any>) => ApiClient.get<{ items: Photo[]; total: number }>('/api/photos', params),
  stats: () => ApiClient.get('/api/photos/stats'),
  get: (id: string) => ApiClient.get<Photo>(`/api/photos/${id}`),
  analyze: (id: string) => ApiClient.post(`/api/photos/${id}/analyze`),
  remove: (id: string) => ApiClient.delete(`/api/photos/${id}`),
  upload: async (files: File[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    const authStore = useAuthStore()
    const response = await axios.post('/api/photos/upload', form, {
      headers: {
        Authorization: `Bearer ${authStore.token || ''}`
      }
    })
    return response.data
  }
}

export const albumApi = {
  list: () => ApiClient.get<Album[]>('/api/albums'),
  get: (id: string) => ApiClient.get<Album>(`/api/albums/${id}`)
}

export const journeyApi = {
  get: () => ApiClient.get<{ points: JourneyPoint[]; segments: any[]; count: number }>('/api/journey')
}

export const recApi = {
  list: () => ApiClient.get<{ items: Recommendation[]; unread: number }>('/api/recommendations'),
  read: (id: string) => ApiClient.post(`/api/recommendations/${id}/read`),
  readAll: () => ApiClient.post('/api/recommendations/read-all')
}

export const chatApi = {
  send: (message: string, model?: { provider?: string; model_name?: string }) =>
    ApiClient.post<{ reply: string }>('/api/chat', { message, ...model }),
  history: () => ApiClient.get<ChatMessage[]>('/api/chat/history')
}

export const configApi = {
  get: () => ApiClient.get('/api/config'),
  update: (data: Record<string, any>) => ApiClient.put('/api/config', data)
}

export function photoFileUrl(id: string, thumb = false) {
  return `/api/photos/${id}/file${thumb ? '?thumb=true' : ''}`
}
