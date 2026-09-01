import { ApiClient } from './request'
import type { Album, ChatMessage, ChatReply, JourneyPoint, ParseQueue, Photo, Recommendation } from '@/types'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

export const photoApi = {
  list: (params?: Record<string, any>) => ApiClient.get<{ items: Photo[]; total: number }>('/api/photos', params),
  stats: () => ApiClient.get('/api/photos/stats'),
  get: (id: string) => ApiClient.get<Photo>(`/api/photos/${id}`),
  analyze: (id: string) => ApiClient.post(`/api/photos/${id}/analyze`),
  parseQueue: () => ApiClient.get<ParseQueue>('/api/photos/parse-queue'),
  reanalyzeBatch: (data?: { include_pending?: boolean; include_failed?: boolean }) =>
    ApiClient.post('/api/photos/reanalyze-batch', data || {}),
  reanalyzeIds: (photo_ids: string[]) => ApiClient.post('/api/photos/reanalyze-ids', { photo_ids }),
  deleteBatch: (photo_ids: string[]) => ApiClient.post('/api/photos/delete-batch', { photo_ids }),
  regeocodeBatch: () => ApiClient.post<{ updated: number }>('/api/photos/regeocode-batch'),
  update: (id: string, data: { tags?: string[]; user_description?: string; user_long_description?: string }) =>
    ApiClient.patch<Photo>(`/api/photos/${id}`, data),
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
  send: (payload: {
    message: string
    provider?: string
    model_name?: string
    photo_ids?: string[]
    top_k?: number
    query_id?: string
    view_more?: boolean
    offset?: number
  }) => ApiClient.post<ChatReply>('/api/chat', payload),
  sendStream: async (
    payload: {
      message: string
      provider?: string
      model_name?: string
      photo_ids?: string[]
      top_k?: number
    },
    handlers: {
      onStatus?: (text: string) => void
      onToken?: (text: string) => void
      onDone?: (data: ChatReply) => void
      onError?: (error: Error) => void
    }
  ) => {
    const authStore = useAuthStore()
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token || ''}`
      },
      body: JSON.stringify(payload)
    })
    if (!response.ok || !response.body) {
      throw new Error(`stream failed: ${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'status') handlers.onStatus?.(event.content || '')
          else if (event.type === 'token') handlers.onToken?.(event.content || '')
          else if (event.type === 'done') handlers.onDone?.(event as ChatReply)
        } catch (err) {
          handlers.onError?.(err as Error)
        }
      }
    }
  },
  history: () => ApiClient.get<ChatMessage[]>('/api/chat/history'),
  inbox: (since?: string) => ApiClient.get<ChatMessage[]>('/api/chat/inbox', since ? { since } : undefined),
  search: (queryId: string, params?: { offset?: number; limit?: number }) =>
    ApiClient.get<ChatReply>(`/api/chat/search/${queryId}`, params)
}

export const configApi = {
  get: () => ApiClient.get('/api/config'),
  update: (data: Record<string, any>) => ApiClient.put('/api/config', data)
}

export function photoFileUrl(id: string, thumb = false) {
  return `/api/photos/${id}/file${thumb ? '?thumb=true' : ''}`
}
